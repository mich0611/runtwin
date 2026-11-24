import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from runtwin.activities.models import Activity, StravaWebhookEvent
from runtwin.activities.webhook import (
    enqueue_webhook_event,
    garmin_provider_from_settings,
    process_pending_webhook_events,
    process_strava_activity,
    process_webhook_event,
    reconcile_recent_strava_runs,
)
from runtwin.providers.garmin import GarminMetricsProvider, GarminUnavailableError
from runtwin.providers.strava_api import StravaApiProvider
from runtwin.providers.strava_publish import ANALYSIS_START


def webhook_payload(**overrides):
    payload = {
        "subscription_id": 123,
        "object_type": "activity",
        "object_id": 987654321,
        "aspect_type": "create",
        "owner_id": 456,
        "event_time": 1780000000,
        "updates": {},
    }
    payload.update(overrides)
    return payload


@override_settings(STRAVA_WEBHOOK_VERIFY_TOKEN="verify-me")
def test_webhook_verification_echoes_challenge(client):
    response = client.get(
        reverse("strava_webhook"),
        {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "abc123"},
    )

    assert response.status_code == 200
    assert response.json() == {"hub.challenge": "abc123"}


@override_settings(STRAVA_WEBHOOK_VERIFY_TOKEN="verify-me")
def test_webhook_verification_rejects_wrong_token(client):
    response = client.get(
        reverse("strava_webhook"),
        {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "abc123"},
    )

    assert response.status_code == 403


@override_settings(STRAVA_WEBHOOK_VERIFY_TOKEN="verify-me")
def test_webhook_verification_rejects_non_ascii_token(client):
    response = client.get(
        reverse("strava_webhook"),
        {"hub.mode": "subscribe", "hub.verify_token": "Ω", "hub.challenge": "abc123"},
    )

    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(
    STRAVA_WEBHOOK_SIGNING_SECRET="sign-me",
    STRAVA_WEBHOOK_REQUIRE_SIGNATURE=True,
    STRAVA_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS=300,
    STRAVA_WEBHOOK_SUBSCRIPTION_ID="123",
    STRAVA_ATHLETE_ID="456",
)
def test_webhook_validates_signature_and_deduplicates(client, monkeypatch):
    monkeypatch.setattr("runtwin.web.views.time.time", lambda: 1_780_000_000)
    body = json.dumps(webhook_payload(), separators=(",", ":")).encode()
    signature = hmac.new(b"sign-me", b"1780000000." + body, hashlib.sha256).hexdigest()
    headers = {"HTTP_X_STRAVA_SIGNATURE": f"t=1780000000,v1={signature}"}

    first = client.post(reverse("strava_webhook"), body, content_type="application/json", **headers)
    second = client.post(reverse("strava_webhook"), body, content_type="application/json", **headers)

    assert first.status_code == 200
    assert first.json()["duplicate"] is False
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert StravaWebhookEvent.objects.count() == 1


@pytest.mark.django_db
@override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID="", STRAVA_ATHLETE_ID="")
def test_webhook_rejects_posts_until_owner_filters_configured(client):
    response = client.post(
        reverse("strava_webhook"),
        data=json.dumps(webhook_payload()),
        content_type="application/json",
    )

    assert response.status_code == 503
    assert StravaWebhookEvent.objects.count() == 0


@pytest.mark.django_db
@override_settings(
    STRAVA_WEBHOOK_SIGNING_SECRET="",
    STRAVA_WEBHOOK_REQUIRE_SIGNATURE=False,
    STRAVA_WEBHOOK_SUBSCRIPTION_ID="123",
    STRAVA_ATHLETE_ID="456",
)
def test_webhook_ignores_unexpected_owner_before_enqueue(client):
    response = client.post(
        reverse("strava_webhook"),
        data=json.dumps(webhook_payload(owner_id=999)),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": True, "ignored": True}
    assert StravaWebhookEvent.objects.count() == 0


@pytest.mark.django_db
@override_settings(
    STRAVA_WEBHOOK_SIGNING_SECRET="sign-me",
    STRAVA_WEBHOOK_REQUIRE_SIGNATURE=True,
    STRAVA_WEBHOOK_SUBSCRIPTION_ID="123",
    STRAVA_ATHLETE_ID="456",
)
def test_webhook_rejects_bad_signature(client):
    response = client.post(
        reverse("strava_webhook"),
        data=json.dumps(webhook_payload()),
        content_type="application/json",
        HTTP_X_STRAVA_SIGNATURE="t=1780000000,v1=bad",
    )

    assert response.status_code == 401
    assert StravaWebhookEvent.objects.count() == 0


class FakeStravaClient:
    def __init__(self, activity=None, streams=None):
        self.activity = activity or {
            "id": 987654321,
            "name": "Morning Run",
            "description": "Original note",
            "start_date_local": "2026-09-16T06:00:00+08:00",
            "sport_type": "Run",
            "distance": 10000,
            "moving_time": 3000,
            "elapsed_time": 3060,
            "total_elevation_gain": 80,
            "average_heartrate": 150,
            "max_heartrate": 170,
        }
        self.streams = streams or {
            "time": {"data": [0, 60, 120, 180]},
            "distance": {"data": [0, 200, 410, 630]},
            "heartrate": {"data": [130, 145, 150, 155]},
            "velocity_smooth": {"data": [3.3, 3.4, 3.5, 3.6]},
            "latlng": {"data": [[25.0, 121.5], [25.0, 121.5], [25.0, 121.5], [25.0, 121.5]]},
        }
        self.updated = None

    def get_activity(self, activity_id):
        return dict(self.activity)

    def get_activity_streams(self, activity_id):
        return self.streams

    def update_activity(self, activity_id, *, name, description):
        self.updated = (activity_id, name, description)
        return {**self.activity, "name": name, "description": description}


class FakeAnalyzer:
    source = "ai:fake"

    def generate(self, activity):
        assert activity.strava_activity_id == "987654321"
        assert activity.has_hr_stream
        return "活動判讀\nAI 分析內容。\n數據觀察\n數據穩定。\n恢復與下一步\n明天輕鬆跑。"


@pytest.mark.django_db
@override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID="123", STRAVA_ATHLETE_ID="456")
def test_process_create_run_imports_analyzes_and_publishes():
    event, _ = enqueue_webhook_event(webhook_payload())
    client = FakeStravaClient()

    status = process_webhook_event(event.pk, client=client, analyzer_factory=FakeAnalyzer)

    assert status == "complete"
    event.refresh_from_db()
    activity = Activity.objects.get(strava_activity_id="987654321")
    assert event.status == StravaWebhookEvent.Status.COMPLETE
    assert event.attempts == 1
    assert activity.analysis_source == "ai:fake"
    assert activity.analysis_generated_at is not None
    assert activity.analysis_published_at is not None
    assert "AI 分析內容" in activity.analysis
    assert client.updated[0] == "987654321"
    assert client.updated[1] == "[Easy] Morning Run"
    assert client.updated[2].startswith("Original note")
    assert client.updated[2].count(ANALYSIS_START) == 1


@pytest.mark.django_db
@override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID="123", STRAVA_ATHLETE_ID="456")
def test_process_non_run_is_ignored_without_streams_or_ai():
    event, _ = enqueue_webhook_event(webhook_payload())
    client = FakeStravaClient(activity={
        "id": 987654321,
        "name": "Ride",
        "description": "",
        "start_date_local": "2026-09-16T06:00:00+08:00",
        "sport_type": "Ride",
        "distance": 20000,
        "moving_time": 3600,
        "elapsed_time": 3600,
    })
    client.get_activity_streams = Mock(side_effect=AssertionError("streams must not be fetched"))

    status = process_webhook_event(event.pk, client=client, analyzer_factory=lambda: Mock())

    assert status == "ignored"
    assert not Activity.objects.exists()
    assert client.updated is None


@pytest.mark.django_db
@override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID="123", STRAVA_ATHLETE_ID="456")
def test_process_ai_failure_uses_deterministic_fallback():
    event, _ = enqueue_webhook_event(webhook_payload())
    client = FakeStravaClient()
    analyzer = Mock()
    analyzer.generate.side_effect = RuntimeError("AI unavailable")

    status = process_webhook_event(event.pk, client=client, analyzer_factory=lambda: analyzer)

    activity = Activity.objects.get(strava_activity_id="987654321")
    assert status == "complete"
    assert activity.analysis_source == "deterministic-fallback"
    assert activity.analysis_version == "activity-analysis-v2"
    assert "🌱 恢復與下一步" in activity.analysis
    assert "🧭 下一步" in activity.analysis
    assert "訓練紀錄不足以看出趨勢" in activity.analysis
    assert client.updated is not None


@pytest.mark.django_db
@override_settings(STRAVA_WEBHOOK_PROCESSING_TIMEOUT_SECONDS=60, STRAVA_WEBHOOK_MAX_ATTEMPTS=3)
def test_pending_processor_requeues_stale_claim(monkeypatch):
    event, _ = enqueue_webhook_event(webhook_payload())
    event.status = StravaWebhookEvent.Status.PROCESSING
    event.attempts = 1
    event.claimed_at = timezone.now() - timedelta(minutes=2)
    event.save(update_fields=["status", "attempts", "claimed_at"])
    monkeypatch.setattr("runtwin.activities.webhook.process_webhook_event", lambda event_id: "complete")

    result = process_pending_webhook_events(limit=10)

    assert not any(result.values())
    event.refresh_from_db()
    assert event.status == StravaWebhookEvent.Status.FAILED
    assert event.next_attempt_at is not None


@pytest.mark.django_db
@override_settings(STRAVA_WEBHOOK_PROCESSING_TIMEOUT_SECONDS=60, STRAVA_WEBHOOK_MAX_ATTEMPTS=3)
def test_pending_processor_marks_final_stale_claim_exhausted(monkeypatch):
    event, _ = enqueue_webhook_event(webhook_payload())
    event.status = StravaWebhookEvent.Status.PROCESSING
    event.attempts = 3
    event.claimed_at = timezone.now() - timedelta(minutes=2)
    event.save(update_fields=["status", "attempts", "claimed_at"])
    process = Mock(side_effect=AssertionError("exhausted event must not run"))
    monkeypatch.setattr("runtwin.activities.webhook.process_webhook_event", process)

    result = process_pending_webhook_events(limit=10)

    assert not any(result.values())
    event.refresh_from_db()
    assert event.status == StravaWebhookEvent.Status.FAILED
    assert "exhausted" in event.error_message
    process.assert_not_called()


@pytest.mark.django_db
def test_reconcile_repairs_missing_webhook_activity(monkeypatch):
    client = FakeStravaClient()
    analyzer_factory = Mock(return_value=FakeAnalyzer())
    monkeypatch.setattr(
        "runtwin.activities.webhook.StravaApiProvider.list_activities",
        lambda self, start=None, end=None: iter([client.activity]),
    )

    result = reconcile_recent_strava_runs(client=client, analyzer_factory=analyzer_factory)

    assert result == {"complete": 1, "ignored": 0, "failed": 0, "skipped": 0}
    activity = Activity.objects.get(strava_activity_id="987654321")
    assert activity.analysis_published_at is not None
    assert client.updated is not None

    second = reconcile_recent_strava_runs(client=client, analyzer_factory=analyzer_factory)
    assert second == {"complete": 0, "ignored": 0, "failed": 0, "skipped": 0}
    assert analyzer_factory.call_count == 1


@pytest.mark.django_db
@override_settings(STRAVA_WEBHOOK_MAX_ATTEMPTS=3)
def test_failed_event_waits_for_backoff(monkeypatch):
    event, _ = enqueue_webhook_event(webhook_payload())
    event.status = StravaWebhookEvent.Status.FAILED
    event.attempts = 1
    event.next_attempt_at = timezone.now() + timedelta(minutes=1)
    event.save(update_fields=["status", "attempts", "next_attempt_at"])
    process = Mock(side_effect=AssertionError("backoff event must not run"))
    monkeypatch.setattr("runtwin.activities.webhook.process_webhook_event", process)

    result = process_pending_webhook_events(limit=10)

    assert not any(result.values())
    process.assert_not_called()


GARMIN_METRICS = {
    "version": "garmin-metrics-v1",
    "garmin_activity_id": "1000000001",
    "aerobic_training_effect": 3.1,
    "hr_zone_seconds": {"2": 1200.0, "3": 600.0},
}


@pytest.mark.django_db
def test_process_strava_activity_stores_matched_garmin_metrics():
    client = FakeStravaClient()
    garmin = Mock()
    garmin.metrics_for_run.return_value = GARMIN_METRICS

    status = process_strava_activity("987654321", client=client, analyzer_factory=FakeAnalyzer, garmin_provider=garmin)

    activity = Activity.objects.get(strava_activity_id="987654321")
    assert status == "complete"
    assert activity.garmin_metrics == GARMIN_METRICS
    start_time, distance = garmin.metrics_for_run.call_args.args
    assert start_time == activity.start_time
    assert distance == 10000
    assert activity.analysis_published_at is not None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("error", "logged"),
    [
        (GarminUnavailableError("Garmin 登入失敗：GarthHTTPError"), "Garmin 登入失敗"),
        (KeyError("secret-looking-detail"), "KeyError"),
    ],
)
def test_process_strava_activity_garmin_failure_still_completes_and_publishes(caplog, error, logged):
    client = FakeStravaClient()
    garmin = Mock()
    garmin.metrics_for_run.side_effect = error

    with caplog.at_level("WARNING", logger="runtwin.activities.webhook"):
        status = process_strava_activity("987654321", client=client, analyzer_factory=FakeAnalyzer, garmin_provider=garmin)

    activity = Activity.objects.get(strava_activity_id="987654321")
    assert status == "complete"
    assert activity.garmin_metrics == {}
    assert activity.analysis_source == "ai:fake"
    assert activity.analysis_published_at is not None
    assert client.updated is not None
    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert len(warnings) == 1
    assert logged in warnings[0].getMessage()
    assert "secret-looking-detail" not in warnings[0].getMessage()


@pytest.mark.django_db
def test_process_strava_activity_without_garmin_enabled_never_builds_provider(settings, monkeypatch):
    settings.RUNTWIN_GARMIN_ENABLED = False
    monkeypatch.setattr(
        "runtwin.activities.webhook.GarminMetricsProvider",
        Mock(side_effect=AssertionError("Garmin provider must not be created")),
    )
    client = FakeStravaClient()

    status = process_strava_activity("987654321", client=client, analyzer_factory=FakeAnalyzer)

    activity = Activity.objects.get(strava_activity_id="987654321")
    assert status == "complete"
    assert activity.garmin_metrics == {}
    assert client.updated is not None


def test_garmin_provider_from_settings_uses_token_dir_when_enabled(settings):
    settings.RUNTWIN_GARMIN_ENABLED = True
    settings.RUNTWIN_GARMIN_TOKEN_DIR = "C:/tokens/garmin"

    provider = garmin_provider_from_settings()

    assert isinstance(provider, GarminMetricsProvider)
    assert provider.token_dir == "C:/tokens/garmin"


def test_garmin_provider_from_settings_returns_none_when_disabled(settings):
    settings.RUNTWIN_GARMIN_ENABLED = False

    assert garmin_provider_from_settings() is None


@pytest.mark.django_db
def test_reconcile_creates_one_garmin_provider_for_all_runs(settings, monkeypatch):
    settings.RUNTWIN_GARMIN_ENABLED = True
    garmin = Mock()
    garmin.metrics_for_run.return_value = GARMIN_METRICS
    provider_class = Mock(return_value=garmin)
    monkeypatch.setattr("runtwin.activities.webhook.GarminMetricsProvider", provider_class)
    client = FakeStravaClient()
    monkeypatch.setattr(
        "runtwin.activities.webhook.StravaApiProvider.list_activities",
        lambda self, start=None, end=None: iter([client.activity]),
    )

    result = reconcile_recent_strava_runs(client=client, analyzer_factory=FakeAnalyzer)

    assert result["complete"] == 1
    provider_class.assert_called_once_with(settings.RUNTWIN_GARMIN_TOKEN_DIR)
    assert Activity.objects.get(strava_activity_id="987654321").garmin_metrics == GARMIN_METRICS


@pytest.mark.django_db
def test_reconcile_filters_non_runs_counts_failures_and_stops_at_limit(monkeypatch):
    payloads = [
        {"id": 1, "sport_type": "Ride"},
        {"id": "not-a-number", "sport_type": "Run"},
        {"id": 2, "sport_type": "Run"},
        {"id": 3, "sport_type": "Run"},
        {"id": 4, "sport_type": "Run"},
    ]
    monkeypatch.setattr(
        "runtwin.activities.webhook.StravaApiProvider.list_activities",
        lambda self, start=None, end=None: iter(payloads),
    )
    processed = []

    def process(activity_id, **kwargs):
        processed.append(activity_id)
        if activity_id == "2":
            raise RuntimeError("Strava down")
        return "unexpected-status"

    monkeypatch.setattr("runtwin.activities.webhook.process_strava_activity", process)

    result = reconcile_recent_strava_runs(limit=2, client=FakeStravaClient(), analyzer_factory=FakeAnalyzer)

    assert processed == ["2", "3"]
    assert result == {"complete": 0, "ignored": 0, "failed": 1, "skipped": 0}


@pytest.mark.django_db
def test_reconcile_limit_counts_only_unpublished_runs(monkeypatch):
    for activity_id in ("10", "11", "12"):
        _local_activity(strava_activity_id=activity_id, analysis_published_at=timezone.now())
    payloads = [{"id": int(activity_id), "sport_type": "Run"} for activity_id in ("10", "11", "12", "13", "14")]
    monkeypatch.setattr(
        "runtwin.activities.webhook.StravaApiProvider.list_activities",
        lambda self, start=None, end=None: iter(payloads),
    )
    processed = []
    monkeypatch.setattr(
        "runtwin.activities.webhook.process_strava_activity",
        lambda activity_id, **kwargs: processed.append(activity_id) or "complete",
    )

    result = reconcile_recent_strava_runs(limit=2, client=FakeStravaClient(), analyzer_factory=FakeAnalyzer)

    assert processed == ["13", "14"]
    assert result["complete"] == 2


def _local_activity(**overrides):
    fields = {
        "strava_activity_id": "987654321",
        "name": "Morning Run",
        "start_time": timezone.now(),
        "sport_type": "Run",
        "distance": 10000,
        "moving_time": 3000,
        "elapsed_time": 3060,
    }
    fields.update(overrides)
    return Activity.objects.create(**fields)


@pytest.mark.django_db
def test_process_strava_activity_already_published_skips_import_and_garmin():
    _local_activity(analysis="done", analysis_source="ai:anthropic", analysis_published_at=timezone.now())
    client = FakeStravaClient()
    client.get_activity_streams = Mock(side_effect=AssertionError("published activity must not re-import"))
    garmin = Mock()

    status = process_strava_activity("987654321", client=client, analyzer_factory=Mock(), garmin_provider=garmin)

    assert status == "complete"
    garmin.metrics_for_run.assert_not_called()
    assert client.updated is None


@pytest.mark.django_db
@pytest.mark.parametrize("previous_source", ["ai:anthropic", "ai:openai", "claude"])
def test_process_strava_activity_keeps_previous_ai_analysis_and_adds_garmin(previous_source):
    _local_activity(analysis="活動判讀\n既有 AI 分析。", analysis_source=previous_source)
    client = FakeStravaClient()
    analyzer_factory = Mock(side_effect=AssertionError("existing AI analysis must be reused"))
    garmin = Mock()
    garmin.metrics_for_run.return_value = GARMIN_METRICS

    status = process_strava_activity("987654321", client=client, analyzer_factory=analyzer_factory, garmin_provider=garmin)

    activity = Activity.objects.get(strava_activity_id="987654321")
    assert status == "complete"
    assert activity.analysis == "活動判讀\n既有 AI 分析。"
    assert activity.analysis_source == previous_source
    assert activity.garmin_metrics == GARMIN_METRICS
    assert "既有 AI 分析" in client.updated[2]


@pytest.mark.django_db
def test_process_strava_activity_skips_when_another_worker_holds_claim():
    _local_activity(analysis_claimed_at=timezone.now())
    client = FakeStravaClient()

    status = process_strava_activity("987654321", client=client, analyzer_factory=FakeAnalyzer)

    assert status == "skipped"
    assert client.updated is None


@pytest.mark.django_db
def test_process_strava_activity_publish_failure_releases_claim():
    client = FakeStravaClient()
    client.update_activity = Mock(side_effect=RuntimeError("Strava write failed"))

    with pytest.raises(RuntimeError, match="Strava write failed"):
        process_strava_activity("987654321", client=client, analyzer_factory=FakeAnalyzer)

    activity = Activity.objects.get(strava_activity_id="987654321")
    assert activity.analysis_claimed_at is None
    assert activity.analysis_published_at is None


def test_strava_provider_unwraps_stream_data():
    provider = StravaApiProvider(client=FakeStravaClient(), activity_ids=["987654321"])

    streams = provider.get_activity_streams("987654321")

    assert streams["heartrate"] == [130, 145, 150, 155]
    assert streams["latlng"][0] == [25.0, 121.5]
