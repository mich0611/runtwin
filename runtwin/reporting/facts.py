from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from django.db.models import QuerySet

from runtwin.activities.models import Activity
from runtwin.athletes.models import AthleteProfile, WellbeingCheckIn
from runtwin.classification.rules import QUALITY_CLASSES
from .periods import normalize_week_start
from .schemas import WeeklyFactsSchema

CALCULATION_VERSION = "weekly-facts-v1"
RUN_TYPES = ["Run", "TrailRun", "VirtualRun"]
ALL_CLASSES = [
    "easy",
    "recovery",
    "long",
    "tempo_threshold",
    "tempo",
    "threshold",
    "fartlek",
    "interval",
    "progression",
    "race",
    "unknown",
]


def metric(value: Any, unit: str, sample_size: int, coverage: float = 1.0, confidence: str = "high", status: str = "ok") -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "sample_size": sample_size,
        "coverage": round(max(0.0, min(1.0, coverage)), 4),
        "confidence": confidence,
        "calculation_version": CALCULATION_VERSION,
        "status": status,
    }


def insufficient(unit: str, sample_size: int = 0, coverage: float = 0.0) -> dict[str, Any]:
    return metric(None, unit, sample_size, coverage, "low", "insufficient_data")


def _activities_for_week(week_start: date, timezone_name: str) -> list[Activity]:
    zone = ZoneInfo(timezone_name)
    start = datetime.combine(week_start, datetime.min.time(), tzinfo=zone)
    end = start + timedelta(days=7)
    return list(Activity.objects.filter(start_time__gte=start, start_time__lt=end, sport_type__in=RUN_TYPES).order_by("start_time"))


def _week_summary(activities: list[Activity]) -> dict[str, float]:
    return {
        "distance_km": sum(item.distance for item in activities) / 1000,
        "moving_minutes": sum(item.moving_time for item in activities) / 60,
        "elevation_m": sum(item.elevation_gain for item in activities),
        "run_count": float(len(activities)),
    }


def _percentage_change(current: float, baseline: float) -> float | None:
    return ((current / baseline) - 1) * 100 if baseline else None


def build_weekly_facts(athlete: AthleteProfile, week_start: date) -> dict[str, Any]:
    week_start = normalize_week_start(week_start)
    week_end = week_start + timedelta(days=6)
    activities = _activities_for_week(week_start, athlete.timezone)
    summary = _week_summary(activities)
    total_distance = sum(item.distance for item in activities)
    total_time = sum(item.moving_time for item in activities)
    longest = max(activities, key=lambda item: item.distance, default=None)
    hr_activities = [item for item in activities if item.average_hr is not None and item.has_hr_stream]
    pace_activities = [item for item in activities if item.average_pace is not None and item.has_pace_stream]
    weighted_hr_seconds = sum(item.moving_time for item in hr_activities)
    weighted_pace_distance = sum(item.distance for item in pace_activities)
    weighted_pace_seconds = sum(item.moving_time for item in pace_activities)
    average_hr = sum(item.average_hr * item.moving_time for item in hr_activities) / weighted_hr_seconds if weighted_hr_seconds else None
    average_pace = weighted_pace_seconds / (weighted_pace_distance / 1000) if weighted_pace_distance else None

    prior_weeks = [week_start - timedelta(days=7 * offset) for offset in range(1, 5)]
    prior_summaries = [_week_summary(_activities_for_week(item, athlete.timezone)) for item in prior_weeks]
    previous = prior_summaries[0]
    four_week = {key: mean(item[key] for item in prior_summaries) for key in summary} if prior_summaries else {}
    historical_weeks = [week_start - timedelta(days=7 * offset) for offset in range(5, -1, -1)]
    six_week = []
    for item in historical_weeks:
        values = _week_summary(_activities_for_week(item, athlete.timezone))
        six_week.append({"week_start": item.isoformat(), **{key: round(value, 2) for key, value in values.items()}})

    distribution = Counter(item.workout_class for item in activities)
    easy_count = distribution["easy"] + distribution["recovery"] + distribution["long"]
    quality_count_for_balance = sum(distribution[key] for key in QUALITY_CLASSES)
    classified_for_balance = easy_count + quality_count_for_balance
    stable = [item for item in activities if item.stream_features.get("steady_run")]
    drift_values = [item.stream_features.get("hr_drift_percent") for item in stable if item.stream_features.get("hr_drift_percent") is not None]
    efficiency_values = [item.stream_features.get("pace_hr_efficiency_m_per_min_per_bpm") for item in activities if item.stream_features.get("pace_hr_efficiency_m_per_min_per_bpm") is not None]
    quality_activities = [item for item in activities if item.workout_class in QUALITY_CLASSES]

    prior_efficiencies: list[float] = []
    for prior_week in prior_weeks:
        for item in _activities_for_week(prior_week, athlete.timezone):
            value = item.stream_features.get("pace_hr_efficiency_m_per_min_per_bpm")
            if value is not None:
                prior_efficiencies.append(value)
    efficiency_change = None
    if efficiency_values and prior_efficiencies:
        efficiency_change = _percentage_change(mean(efficiency_values), mean(prior_efficiencies))

    metrics = {
        "run_count": metric(len(activities), "次", len(activities)),
        "total_distance": metric(round(summary["distance_km"], 2), "km", len(activities)),
        "total_moving_time": metric(round(summary["moving_minutes"], 1), "分鐘", len(activities)),
        "total_elevation_gain": metric(round(summary["elevation_m"], 1), "m", len(activities)),
        "longest_run_distance": metric(round(longest.distance / 1000, 2), "km", 1) if longest else insufficient("km"),
        "longest_run_time": metric(round(longest.moving_time / 60, 1), "分鐘", 1) if longest else insufficient("分鐘"),
        "average_pace": metric(round(average_pace, 1), "秒/km", len(pace_activities), weighted_pace_distance / total_distance if total_distance else 0, "medium") if average_pace else insufficient("秒/km", len(pace_activities)),
        "average_hr": metric(round(average_hr, 1), "bpm", len(hr_activities), weighted_hr_seconds / total_time if total_time else 0, "medium") if average_hr else insufficient("bpm", len(hr_activities)),
        "quality_session_count": metric(len(quality_activities), "次", len(activities)),
        "easy_quality_balance": metric({"easy_recovery_long": easy_count, "quality": quality_count_for_balance}, "次", classified_for_balance, classified_for_balance / len(activities) if activities else 0, "medium") if classified_for_balance else insufficient("次"),
        "steady_run_hr_drift": metric(round(mean(drift_values), 2), "%", len(drift_values), len(drift_values) / len(activities) if activities else 0, "medium") if drift_values else insufficient("%", 0),
        "pace_hr_efficiency": metric(round(mean(efficiency_values), 4), "m/min/bpm", len(efficiency_values), len(efficiency_values) / len(activities) if activities else 0, "medium") if efficiency_values else insufficient("m/min/bpm", 0),
        "pace_hr_efficiency_vs_four_week": metric(round(efficiency_change, 2), "%", len(efficiency_values), min(1, len(prior_efficiencies) / 4), "low") if efficiency_change is not None else insufficient("%", len(efficiency_values)),
    }

    comparisons: dict[str, Any] = {}
    for key, label in (("distance_km", "distance"), ("moving_minutes", "moving_time"), ("elevation_m", "elevation"), ("run_count", "run_count")):
        prev_change = _percentage_change(summary[key], previous[key])
        avg_change = _percentage_change(summary[key], four_week[key])
        comparisons[f"{label}_vs_previous_week"] = metric(round(prev_change, 1), "%", 1, confidence="medium") if prev_change is not None else insufficient("%")
        comparisons[f"{label}_vs_four_week_average"] = metric(round(avg_change, 1), "%", 4, confidence="medium") if avg_change is not None else insufficient("%", 4)

    profile_distance = float(athlete.normal_weekly_distance)
    baseline_delta = _percentage_change(summary["distance_km"], profile_distance) if profile_distance > 0 else None
    anomaly_flags: list[dict[str, Any]] = []
    if baseline_delta is not None and abs(baseline_delta) >= 25:
        anomaly_flags.append({"type": "weekly_distance", "severity": "warning", "delta_percent": round(baseline_delta, 1), "message": "本週跑量明顯偏離個人通常週量。"})
    elevation_delta = comparisons["elevation_vs_four_week_average"].get("value")
    if elevation_delta is not None and abs(elevation_delta) >= 50:
        anomaly_flags.append({"type": "elevation", "severity": "warning", "delta_percent": elevation_delta, "message": "本週爬升明顯偏離四週平均。"})
    checkin = WellbeingCheckIn.objects.filter(athlete=athlete, week_start=week_start).first()
    wellbeing = None
    if checkin:
        wellbeing = {key: getattr(checkin, key) for key in ("sleep_quality", "fatigue", "soreness", "knee_pain", "motivation", "notes")}
        if checkin.knee_pain >= 4 or checkin.fatigue >= 7 or checkin.soreness >= 7:
            anomaly_flags.append({"type": "recovery", "severity": "high", "message": "主觀狀態顯示疼痛或恢復風險，建議降載。"})

    quality_issues = []
    for activity in activities:
        for issue in activity.quality_issues:
            quality_issues.append({"activity_id": activity.strava_activity_id, "date": activity.start_time.astimezone(ZoneInfo(athlete.timezone)).date().isoformat(), **issue})
    quality_scores = [item.data_quality_score for item in activities]

    payload = {
        "schema_version": "weekly-facts-v1",
        "calculation_version": CALCULATION_VERSION,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "athlete_profile": {
            "half_marathon_pb_seconds": athlete.half_marathon_pb.total_seconds() if athlete.half_marathon_pb else None,
            "half_marathon_goal_seconds": athlete.half_marathon_goal.total_seconds() if athlete.half_marathon_goal else None,
            "marathon_goal_seconds": athlete.marathon_goal.total_seconds() if athlete.marathon_goal else None,
            "normal_weekly_distance_km": profile_distance,
            "runs_per_week": athlete.runs_per_week,
            "weekday_distance_limit_km": float(athlete.weekday_distance_limit),
            "preferred_long_run_days": athlete.preferred_long_run_days,
            "provisional_tempo_hr_bpm": [athlete.provisional_tempo_hr_low, athlete.provisional_tempo_hr_high],
            "observed_hr_max_bpm": athlete.observed_hr_max,
            "external_vo2max_reference": [float(athlete.garmin_vo2max_reference_low) if athlete.garmin_vo2max_reference_low else None, float(athlete.garmin_vo2max_reference_high) if athlete.garmin_vo2max_reference_high else None],
            "constraints": ["Phase 1 不估算 LT1/LT2", "Phase 1 不預測比賽成績"],
        },
        "metrics": metrics,
        "comparisons": comparisons,
        "trends": {"six_week": six_week, "anomaly_flags": anomaly_flags},
        "workout_distribution": {item: metric(distribution[item], "次", len(activities)) for item in ALL_CLASSES},
        "activities": [{"activity_id": item.strava_activity_id, "date": item.start_time.astimezone(ZoneInfo(athlete.timezone)).date().isoformat(), "name": item.name} for item in activities],
        "activity_facts": [{
            "activity_id": item.strava_activity_id,
            "date": item.start_time.astimezone(ZoneInfo(athlete.timezone)).date().isoformat(),
            "name": item.name,
            "distance_km": round(item.distance / 1000, 2),
            "moving_minutes": round(item.moving_time / 60, 1),
            "elevation_gain_m": round(item.elevation_gain, 1),
            "average_pace_seconds_per_km": round(item.average_pace, 1) if item.average_pace else None,
            "average_hr_bpm": round(item.average_hr, 1) if item.average_hr else None,
            "workout_class": item.workout_class,
            "classification_confidence": item.classification_confidence,
            "classification_reasons": item.classification_reasons,
            "data_quality_score": item.data_quality_score,
            "quality_issues": item.quality_issues,
            "stream_features": item.stream_features,
        } for item in activities],
        "quality": {
            "average_score": round(mean(quality_scores), 1) if quality_scores else None,
            "issues": quality_issues,
            "hr_activity_coverage": round(len(hr_activities) / len(activities), 4) if activities else 0,
            "pace_activity_coverage": round(len(pace_activities) / len(activities), 4) if activities else 0,
        },
        "wellbeing": wellbeing,
    }
    return WeeklyFactsSchema.model_validate(payload).model_dump(mode="json")
