from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from runtwin.activities.models import Activity, ActivityStream, DataSyncRun
from runtwin.athletes.models import AthleteProfile
from runtwin.classification.rules import classify_activity
from runtwin.classification.title import strip_run_type_prefix
from runtwin.features.activity import calculate_stream_features
from runtwin.features.activity_analysis import build_activity_analysis
from runtwin.providers.base import StravaDataProvider
from runtwin.providers.strava_publish import strip_analysis_from_description
from runtwin.quality.checks import assess_stream_quality

STREAM_ALIASES = {
    "heartrate": "heart_rate",
    "velocity_smooth": "velocity",
    "grade_smooth": "grade",
    "latlng": "gps",
    "location": "gps",
}


def _parse_start(value: str, timezone_name: str = "Asia/Taipei") -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed


def _normalized_streams(streams: dict[str, Any]) -> dict[str, list[Any]]:
    normalized: dict[str, list[Any]] = {}
    for key, value in streams.items():
        if isinstance(value, dict):
            value = value.get("data")
        if isinstance(value, list):
            normalized[STREAM_ALIASES.get(key, key)] = value
    return normalized


def _summary(activity: dict[str, Any]) -> dict[str, Any]:
    return activity.get("summary", activity)


def _recent_distance_percentile(distance: float, reference_distances: tuple[float, ...]) -> float | None:
    if not reference_distances:
        return None
    return sum(value <= distance for value in reference_distances) / len(reference_distances)


@transaction.atomic
def _import_provider_atomic(provider: StravaDataProvider, source: str = "snapshot") -> dict[str, int]:
    created_count = 0
    updated_count = 0
    stream_count = 0
    payloads = list(provider.list_activities())
    batch_ids = {str(payload.get("id") or payload.get("strava_activity_id")) for payload in payloads}
    reference_distances = tuple(
        Activity.objects.filter(sport_type__in=["Run", "TrailRun", "VirtualRun"])
        .exclude(strava_activity_id__in=batch_ids)
        .order_by("-start_time")
        .values_list("distance", flat=True)[:40]
    )
    profile = AthleteProfile.objects.order_by("id").first()
    tempo_hr_low = profile.provisional_tempo_hr_low if profile else None
    for payload in payloads:
        activity_id = str(payload.get("id") or payload.get("strava_activity_id"))
        if not activity_id or activity_id == "None":
            continue
        summary = _summary(payload)
        start_value = payload.get("start_time") or payload.get("start_date") or payload.get("start_local") or payload.get("start_date_local")
        if not start_value:
            continue
        distance = float(summary.get("distance") or payload.get("distance") or 0)
        moving_time = int(summary.get("moving_time") or payload.get("moving_time") or 0)
        elapsed_time = int(summary.get("elapsed_time") or payload.get("elapsed_time") or moving_time)
        streams = _normalized_streams(provider.get_activity_streams(activity_id))
        quality = assess_stream_quality(streams, moving_time, elapsed_time)
        features = calculate_stream_features(streams, moving_time, distance)
        user_name = strip_run_type_prefix(payload.get("name", "未命名活動"))
        user_description = strip_analysis_from_description(payload.get("description", ""))
        classification = classify_activity(
            name=user_name,
            description=user_description,
            distance_m=distance,
            moving_time_s=moving_time,
            features=features,
            recent_distance_percentile=_recent_distance_percentile(distance, reference_distances),
            summary=summary,
            tempo_hr_low=tempo_hr_low,
        )
        valid_hr = [value for value in streams.get("heart_rate", []) if isinstance(value, (int, float)) and 30 <= value <= 230]
        average_hr = summary.get("average_heartrate", summary.get("average_hr"))
        max_hr = summary.get("max_heartrate", summary.get("max_hr"))
        if average_hr is None and valid_hr:
            average_hr = mean(valid_hr)
        if max_hr is None and valid_hr:
            max_hr = max(valid_hr)
        defaults = {
            "name": user_name,
            "description": user_description,
            "start_time": _parse_start(start_value),
            "sport_type": payload.get("sport_type", "Run"),
            "distance": distance,
            "moving_time": moving_time,
            "elapsed_time": elapsed_time,
            "elevation_gain": float(
                summary.get("total_elevation_gain")
                or summary.get("elevation_gain")
                or payload.get("total_elevation_gain")
                or payload.get("elevation_gain")
                or 0
            ),
            "average_hr": average_hr,
            "max_hr": max_hr,
            "average_pace": moving_time / (distance / 1000) if distance else None,
            "workout_class": classification["workout_class"],
            "classification_confidence": classification["confidence"],
            "classification_reasons": classification["reasons"],
            "classifier_version": classification["classifier_version"],
            "source": source,
            "data_quality_score": quality["score"],
            "quality_issues": quality["issues"],
            "quality_version": quality["quality_version"],
            "has_hr_stream": quality["has_hr_stream"],
            "has_pace_stream": quality["has_pace_stream"],
            "has_altitude_stream": quality["has_altitude_stream"],
            "stream_features": features,
            "raw_summary": summary,
        }
        activity, created = Activity.objects.update_or_create(strava_activity_id=activity_id, defaults=defaults)
        created_count += int(created)
        updated_count += int(not created)
        if streams:
            ActivityStream.objects.update_or_create(
                activity=activity,
                defaults={
                    "time": streams.get("time", []),
                    "distance": streams.get("distance", []),
                    "heart_rate": streams.get("heart_rate", []),
                    "velocity": streams.get("velocity", []),
                    "altitude": streams.get("altitude", []),
                    "grade": streams.get("grade_smooth", streams.get("grade", [])),
                    "cadence": streams.get("cadence", []),
                    "moving": streams.get("moving", []),
                    "gps": streams.get("gps", []),
                    "sample_count": quality["sample_count"],
                    "source_resolution": None,
                },
            )
            stream_count += 1
        else:
            ActivityStream.objects.filter(activity=activity).delete()
        if activity.sport_type in {"Run", "TrailRun", "VirtualRun"} and (created or not activity.analysis):
            try:
                activity.analysis = build_activity_analysis(activity)
                activity.analysis_source = "deterministic"
                activity.analysis_version = "activity-analysis-v1"
                activity.analysis_generated_at = timezone.now()
                activity.save(update_fields=["analysis", "analysis_source", "analysis_version", "analysis_generated_at"])
            except Exception:
                # Analysis is supplementary and must never block a successful sync.
                pass
    return {"created": created_count, "updated": updated_count, "streams": stream_count}


def import_provider(provider: StravaDataProvider, source: str = "snapshot") -> dict[str, int]:
    sync_run = DataSyncRun.objects.create(source=source)
    try:
        result = _import_provider_atomic(provider, source)
    except Exception as exc:
        sync_run.status = "failed"
        sync_run.error_message = f"{type(exc).__name__}: {exc}"[:4000]
        sync_run.completed_at = timezone.now()
        sync_run.save(update_fields=["status", "error_message", "completed_at"])
        raise
    sync_run.status = "complete"
    sync_run.activities_created = result["created"]
    sync_run.activities_updated = result["updated"]
    sync_run.streams_imported = result["streams"]
    sync_run.completed_at = timezone.now()
    sync_run.save(update_fields=["status", "activities_created", "activities_updated", "streams_imported", "completed_at"])
    return result
