from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Callable

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from runtwin.activities.models import Activity, StravaWebhookEvent
from runtwin.ai.activity import ACTIVITY_ANALYSIS_PROMPT_VERSION, ActivityAnalyzer, build_training_history
from runtwin.features.activity_analysis import ANALYSIS_VERSION, build_activity_analysis
from runtwin.ingestion.service import import_provider
from runtwin.providers.garmin import GarminMetricsProvider, GarminUnavailableError
from runtwin.providers.strava_api import StravaApiProvider
from runtwin.providers.strava_publish import publish_activity_analysis
from runtwin.providers.strava_write import StravaWriteClient

RUN_SPORT_TYPES = {"Run", "TrailRun", "VirtualRun"}
# Older databases tagged LLM output as "claude"; newer ones use "ai:<provider>".
LEGACY_AI_SOURCES = {"claude"}
logger = logging.getLogger(__name__)


def enqueue_webhook_event(payload: dict[str, Any]) -> tuple[StravaWebhookEvent, bool]:
    event, created = StravaWebhookEvent.objects.get_or_create(
        subscription_id=_required_int(payload, "subscription_id"),
        object_type=_required_string(payload, "object_type"),
        object_id=_required_int(payload, "object_id"),
        aspect_type=_required_string(payload, "aspect_type"),
        event_time=_required_int(payload, "event_time"),
        defaults={
            "owner_id": _required_int(payload, "owner_id"),
            "updates": payload.get("updates") if isinstance(payload.get("updates"), dict) else {},
        },
    )
    return event, created


def process_pending_webhook_events(*, limit: int = 20) -> dict[str, int]:
    counts = {"complete": 0, "ignored": 0, "failed": 0, "skipped": 0}
    stale_before = timezone.now() - timedelta(seconds=settings.STRAVA_WEBHOOK_PROCESSING_TIMEOUT_SECONDS)
    stale = StravaWebhookEvent.objects.filter(
        status=StravaWebhookEvent.Status.PROCESSING,
        claimed_at__lt=stale_before,
    )
    stale.filter(attempts__lt=settings.STRAVA_WEBHOOK_MAX_ATTEMPTS).update(
        status=StravaWebhookEvent.Status.FAILED,
        error_message="Worker processing timeout; queued for retry.",
        next_attempt_at=timezone.now() + timedelta(seconds=60),
        processed_at=timezone.now(),
    )
    stale.filter(attempts__gte=settings.STRAVA_WEBHOOK_MAX_ATTEMPTS).update(
        status=StravaWebhookEvent.Status.FAILED,
        error_message="Worker processing timeout; retry limit exhausted.",
        next_attempt_at=None,
        processed_at=timezone.now(),
    )
    ids = list(
        StravaWebhookEvent.objects.filter(
            status__in=[StravaWebhookEvent.Status.PENDING, StravaWebhookEvent.Status.FAILED],
            attempts__lt=settings.STRAVA_WEBHOOK_MAX_ATTEMPTS,
        ).filter(
            Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=timezone.now())
        ).order_by("received_at").values_list("id", flat=True)[:limit]
    )
    for event_id in ids:
        status = process_webhook_event(event_id)
        counts[status] += 1
    return counts


def reconcile_recent_strava_runs(
    *,
    days: int = 3,
    limit: int = 100,
    client: StravaWriteClient | Any | None = None,
    analyzer_factory: Callable[[], Any] | None = None,
) -> dict[str, int]:
    client = client or StravaWriteClient.from_settings()
    provider = StravaApiProvider(client=client)
    garmin_provider = garmin_provider_from_settings()
    start = timezone.now() - timedelta(days=max(1, days))
    counts = {"complete": 0, "ignored": 0, "failed": 0, "skipped": 0}
    examined = 0
    for payload in provider.list_activities(start=start):
        if examined >= max(1, limit):
            break
        activity_id = str(payload.get("id", ""))
        if not activity_id.isdigit() or payload.get("sport_type") not in RUN_SPORT_TYPES:
            continue
        # Strava lists `after=` results oldest first; already-published runs must not consume
        # the limit, otherwise a long window could stop before reaching the newest unpublished runs.
        if Activity.objects.filter(
            strava_activity_id=activity_id,
            analysis_published_at__isnull=False,
        ).exists():
            continue
        examined += 1
        try:
            status = process_strava_activity(
                activity_id,
                client=client,
                analyzer_factory=analyzer_factory,
                garmin_provider=garmin_provider,
            )
        except Exception:
            logger.exception("Reconciliation failed for Strava activity %s", activity_id)
            counts["failed"] += 1
        else:
            if status in counts:
                counts[status] += 1
    return counts


def process_strava_activity(
    activity_id: str,
    *,
    client: StravaWriteClient | Any | None = None,
    analyzer_factory: Callable[[], Any] | None = None,
    garmin_provider: GarminMetricsProvider | Any | None = None,
) -> str:
    client = client or StravaWriteClient.from_settings()
    analyzer_factory = analyzer_factory or ActivityAnalyzer
    garmin_provider = garmin_provider or garmin_provider_from_settings()
    provider = StravaApiProvider(client=client, activity_ids=[str(activity_id)])
    activity_payload = provider.get_activity_details(str(activity_id))
    if activity_payload.get("sport_type") not in RUN_SPORT_TYPES:
        return "ignored"

    activity = Activity.objects.filter(strava_activity_id=str(activity_id)).first()
    if activity is None or activity.analysis_published_at is None:
        previous_analysis_source = activity.analysis_source if activity else ""
        previous_analysis = activity.analysis if activity else ""
        import_provider(provider, source="strava_api")
        activity = Activity.objects.get(strava_activity_id=str(activity_id))
        _attach_garmin_metrics(activity, garmin_provider)
        if is_ai_source(previous_analysis_source) and previous_analysis.strip():
            activity.analysis = previous_analysis
            activity.analysis_source = previous_analysis_source
            activity.save(update_fields=["analysis", "analysis_source"])

    if activity.analysis_published_at is not None:
        return "complete"
    if not _claim_activity_analysis(activity.pk):
        return "skipped"

    try:
        _analyze_and_publish(activity, client, analyzer_factory)
    except Exception:
        Activity.objects.filter(pk=activity.pk).update(analysis_claimed_at=None)
        raise
    return "complete"


def is_ai_source(source: str | None) -> bool:
    source = source or ""
    return source == "ai" or source.startswith("ai:") or source in LEGACY_AI_SOURCES


def garmin_provider_from_settings() -> GarminMetricsProvider | None:
    if not settings.RUNTWIN_GARMIN_ENABLED:
        return None
    return GarminMetricsProvider(settings.RUNTWIN_GARMIN_TOKEN_DIR)


def _attach_garmin_metrics(activity: Activity, garmin_provider: Any | None) -> None:
    """Garmin is supplementary: any failure is logged and the Strava pipeline continues."""
    if garmin_provider is None:
        return
    try:
        metrics = garmin_provider.metrics_for_run(activity.start_time, activity.distance)
    except GarminUnavailableError as exc:
        logger.warning("Garmin metrics unavailable for activity %s: %s", activity.strava_activity_id, exc)
        return
    except Exception as exc:
        logger.warning("Garmin metrics failed for activity %s: %s", activity.strava_activity_id, type(exc).__name__)
        return
    activity.garmin_metrics = metrics
    activity.save(update_fields=["garmin_metrics"])


def _claim_activity_analysis(activity_id: int) -> bool:
    stale_before = timezone.now() - timedelta(seconds=settings.STRAVA_WEBHOOK_PROCESSING_TIMEOUT_SECONDS)
    updated = Activity.objects.filter(
        Q(analysis_claimed_at__isnull=True) | Q(analysis_claimed_at__lt=stale_before),
        pk=activity_id,
        analysis_published_at__isnull=True,
    ).update(analysis_claimed_at=timezone.now())
    return updated == 1


def process_webhook_event(
    event_id: int,
    *,
    client: StravaWriteClient | Any | None = None,
    analyzer_factory: Callable[[], Any] | None = None,
) -> str:
    event = _claim_event(event_id)
    if event is None:
        return "skipped"

    client = client or StravaWriteClient.from_settings()
    analyzer_factory = analyzer_factory or ActivityAnalyzer
    try:
        status = _process_claimed_event(event, client, analyzer_factory)
    except Exception as exc:
        event.status = StravaWebhookEvent.Status.FAILED
        event.error_message = f"{type(exc).__name__}: {exc}"[:4000]
        event.processed_at = timezone.now()
        event.next_attempt_at = _next_attempt_at(event.attempts)
        event.save(update_fields=["status", "error_message", "processed_at", "next_attempt_at"])
        logger.exception("Strava webhook event %s failed", event.pk)
        return "failed"

    if status == "skipped":
        event.status = StravaWebhookEvent.Status.PENDING
        event.attempts = max(0, event.attempts - 1)
        event.next_attempt_at = timezone.now() + timedelta(seconds=60)
        event.save(update_fields=["status", "attempts", "next_attempt_at"])
        return status
    event.status = status
    event.error_message = ""
    event.next_attempt_at = None
    event.processed_at = timezone.now()
    event.save(update_fields=["status", "error_message", "next_attempt_at", "processed_at"])
    return status


@transaction.atomic
def _claim_event(event_id: int) -> StravaWebhookEvent | None:
    event = StravaWebhookEvent.objects.select_for_update().get(pk=event_id)
    if event.status in {
        StravaWebhookEvent.Status.COMPLETE,
        StravaWebhookEvent.Status.IGNORED,
        StravaWebhookEvent.Status.PROCESSING,
    }:
        return None
    if event.attempts >= settings.STRAVA_WEBHOOK_MAX_ATTEMPTS:
        return None
    event.status = StravaWebhookEvent.Status.PROCESSING
    event.attempts += 1
    event.claimed_at = timezone.now()
    event.save(update_fields=["status", "attempts", "claimed_at"])
    return event


def _process_claimed_event(event: StravaWebhookEvent, client: Any, analyzer_factory: Callable[[], Any]) -> str:
    if event.object_type != "activity" or event.aspect_type != "create":
        return "ignored"
    if not settings.STRAVA_WEBHOOK_SUBSCRIPTION_ID or not settings.STRAVA_ATHLETE_ID:
        raise RuntimeError("自動處理需要設定 STRAVA_WEBHOOK_SUBSCRIPTION_ID 與 STRAVA_ATHLETE_ID。")
    if str(event.subscription_id) != settings.STRAVA_WEBHOOK_SUBSCRIPTION_ID:
        return "ignored"
    if str(event.owner_id) != settings.STRAVA_ATHLETE_ID:
        return "ignored"

    try:
        return process_strava_activity(
            str(event.object_id),
            client=client,
            analyzer_factory=analyzer_factory,
        )
    except Exception:
        logger.exception("Processing failed for Strava webhook event %s", event.pk)
        raise


def _analyze_and_publish(activity: Activity, client: Any, analyzer_factory: Callable[[], Any]) -> None:
    if not (is_ai_source(activity.analysis_source) and activity.analysis.strip()):
        try:
            analyzer = analyzer_factory()
            analysis = analyzer.generate(activity)
            source = getattr(analyzer, "source", "ai")
            version = ACTIVITY_ANALYSIS_PROMPT_VERSION
        except Exception:
            logger.exception("AI generation failed for activity %s; using deterministic fallback", activity.strava_activity_id)
            analysis = build_activity_analysis(activity, build_training_history(activity))
            source = "deterministic-fallback"
            version = ANALYSIS_VERSION

        activity.analysis = analysis
        activity.analysis_source = source
        activity.analysis_version = version
        activity.analysis_generated_at = timezone.now()
        activity.save(update_fields=["analysis", "analysis_source", "analysis_version", "analysis_generated_at"])

    publish_activity_analysis(activity, client, remote=activity.raw_summary or None)
    activity.analysis_published_at = timezone.now()
    activity.analysis_claimed_at = None
    activity.save(update_fields=["analysis_published_at", "analysis_claimed_at"])


def _next_attempt_at(attempts: int):
    if attempts >= settings.STRAVA_WEBHOOK_MAX_ATTEMPTS:
        return None
    delay_seconds = min(3600, 60 * (2 ** max(0, attempts - 1)))
    return timezone.now() + timedelta(seconds=delay_seconds)


def _required_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool):
        raise ValueError(f"Webhook 欄位 {key} 必須是整數。")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Webhook 缺少有效的 {key}。") from exc


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Webhook 缺少有效的 {key}。")
    return value
