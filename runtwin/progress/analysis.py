from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, median
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from runtwin.activities.models import Activity
from runtwin.classification.rules import QUALITY_CLASSES

MODEL_VERSION = "progress-association-v2"
MIN_COMPLETE_WEEKS = 8
MAX_LOOKBACK_WEEKS = 78
CONTEXT_WEEKS = 12
MIN_TREND_WEEKS = 6
HIGH_DEW_POINT_C = 18.0


@dataclass(frozen=True)
class FactorDefinition:
    key: str
    label: str
    unit: str
    direction: str
    source: str = "strava"


FACTORS = (
    FactorDefinition("distance_km", "週跑量", "km／週", "higher"),
    FactorDefinition("run_count", "跑步頻率", "次／週", "higher"),
    FactorDefinition("longest_run_km", "最長跑距離", "km", "higher"),
    FactorDefinition("long_run_count", "長跑頻率", "次／週", "higher"),
    FactorDefinition("quality_count", "品質課頻率", "次／週", "higher"),
    FactorDefinition("easy_share", "Easy／恢復／長跑占比", "%", "higher"),
    FactorDefinition("stable_hr_drift", "穩定跑心率漂移", "%", "lower"),
    FactorDefinition("garmin_training_load", "Garmin 週訓練負荷", "load／週", "higher", "garmin"),
    FactorDefinition("garmin_aerobic_te", "Garmin 平均有氧訓練效果", "TE", "higher", "garmin"),
    FactorDefinition("garmin_z2_share", "Garmin 心率 Z1–Z2 占比", "%", "higher", "garmin"),
    FactorDefinition("garmin_high_dew_point_runs", "Garmin 高露點跑步次數", "次／週", "lower", "garmin"),
)
GARMIN_WEEKLY_KEYS = tuple(item.key for item in FACTORS if item.source == "garmin")


def build_progress_analysis(activities: Iterable[Activity] | None = None, *, today: date | None = None, timezone_name: str = "Asia/Taipei") -> dict[str, Any]:
    zone = ZoneInfo(timezone_name)
    today = today or date.today()
    current_week = today - timedelta(days=today.weekday())
    start_week = current_week - timedelta(weeks=MAX_LOOKBACK_WEEKS)
    if activities is None:
        activities = Activity.objects.filter(
            sport_type__in=["Run", "TrailRun", "VirtualRun"],
            start_time__gte=_week_datetime(start_week, zone),
            start_time__lt=_week_datetime(current_week, zone),
        ).order_by("start_time")
    weeks = _weekly_rows(list(activities), current_week=current_week, zone=zone)
    outcome_weeks = [row for row in weeks if row["efficiency"] is not None]
    garmin_week_count = sum(1 for row in weeks if row["garmin_run_count"])
    base = {
        "model_version": MODEL_VERSION,
        "generated_for_week": current_week.isoformat(),
        "complete_week_count": len(weeks),
        "outcome_week_count": len(outcome_weeks),
        "outcome_label": "Easy／Long 跑的配速心率效率（m/min/bpm）",
        "status": "insufficient_data",
        "confidence": "low",
        "summary": "歷史資料不足，至少需要 8 個完整週且多週具有效率資料，才會顯示個人化關聯。",
        "factors": [],
        "trend": [],
        "garmin_week_count": garmin_week_count,
        "training_context": build_training_context(weeks),
        "limitations": [
            "這是個人歷史中的預測關聯，不代表因果關係。",
            "天氣、路線、睡眠、疾病與量測裝置可能同時影響結果。",
            "模型不預測比賽成績，也不取代教練或醫療判斷。",
            "Garmin 因素只計入能和 Strava 配對的跑步；Garmin 資料週數不足時不會列入關聯。",
        ],
    }
    if len(weeks) < MIN_COMPLETE_WEEKS or len(outcome_weeks) < 6:
        return base

    factors = []
    for definition in FACTORS:
        pairs = []
        for index, week in enumerate(weeks[:-1]):
            next_week = weeks[index + 1]
            value = week.get(definition.key)
            outcome = next_week.get("efficiency")
            if value is not None and outcome is not None:
                pairs.append((float(value), float(outcome)))
        if len(pairs) < 6 or len({value for value, _ in pairs}) < 3:
            continue
        correlation = _spearman([value for value, _ in pairs], [outcome for _, outcome in pairs])
        if correlation is None:
            continue
        favorable = correlation if definition.direction == "higher" else -correlation
        recent_values = [row[definition.key] for row in weeks[-4:] if row.get(definition.key) is not None]
        factors.append({
            "key": definition.key,
            "label": definition.label,
            "unit": definition.unit,
            "source": definition.source,
            "sample_size": len(pairs),
            "correlation": round(correlation, 3),
            "favorable_score": round(favorable, 3),
            "strength": _strength(abs(correlation)),
            "confidence": _factor_confidence(abs(correlation), len(pairs)),
            "direction_text": _direction_text(definition, correlation),
            "recent_value": round(mean(recent_values), 2) if recent_values else None,
        })
    factors.sort(key=lambda item: (item["confidence"] != "low", abs(item["favorable_score"]), item["sample_size"]), reverse=True)
    supported = [item for item in factors if item["confidence"] != "low" and abs(item["correlation"]) >= 0.2]
    trend = [
        {"week_start": row["week_start"].isoformat(), "efficiency": round(row["efficiency"], 4)}
        for row in weeks[-12:]
        if row["efficiency"] is not None
    ]
    base.update({
        "status": "ok" if supported else "limited",
        "confidence": "high" if len(outcome_weeks) >= 20 and supported else "medium" if supported else "low",
        "summary": (
            f"以 {len(weeks)} 個完整週、{len(outcome_weeks)} 個有效率資料週做時間先後關聯；"
            f"目前有 {len(supported)} 個因素達到可顯示門檻。"
            if supported
            else f"已有 {len(weeks)} 個完整週，但目前沒有穩定到足以列為重點的關聯。"
        ),
        # Cap per source so Garmin factors are not crowded out by the longer Strava history.
        "factors": [item for item in supported if item["source"] == "strava"][:6]
        + [item for item in supported if item["source"] == "garmin"][:4],
        "trend": trend,
    })
    return base


def _weekly_rows(activities: list[Activity], *, current_week: date, zone: ZoneInfo) -> list[dict[str, Any]]:
    grouped: dict[date, list[Activity]] = {}
    for activity in activities:
        local_day = activity.start_time.astimezone(zone).date()
        week_start = local_day - timedelta(days=local_day.weekday())
        if week_start >= current_week:
            continue
        grouped.setdefault(week_start, []).append(activity)
    if not grouped:
        return []
    first = max(min(grouped), current_week - timedelta(weeks=MAX_LOOKBACK_WEEKS))
    rows = []
    week = first
    while week < current_week:
        items = grouped.get(week, [])
        quality_count = sum(item.workout_class in QUALITY_CLASSES for item in items)
        easy_count = sum(item.workout_class in {"easy", "recovery", "long"} for item in items)
        classified = easy_count + quality_count
        efficiencies = [
            float(item.stream_features["pace_hr_efficiency_m_per_min_per_bpm"])
            for item in items
            if item.workout_class in {"easy", "long"}
            and item.moving_time >= 30 * 60
            and item.stream_features.get("pace_hr_efficiency_m_per_min_per_bpm") is not None
        ]
        drift = [
            float(item.stream_features["hr_drift_percent"])
            for item in items
            if item.stream_features.get("steady_run")
            and item.stream_features.get("hr_drift_percent") is not None
        ]
        rows.append({
            "week_start": week,
            "distance_km": sum(item.distance for item in items) / 1000,
            "run_count": len(items),
            "longest_run_km": max((item.distance for item in items), default=0) / 1000,
            "long_run_count": sum(item.workout_class == "long" for item in items),
            "quality_count": quality_count,
            "easy_share": (easy_count / classified * 100) if classified else None,
            "stable_hr_drift": median(drift) if drift else None,
            "efficiency": median(efficiencies) if efficiencies else None,
            "class_counts": {cls: sum(item.workout_class == cls for item in items) for cls in sorted({item.workout_class for item in items})},
            "easy_efficiency_values": [
                float(item.stream_features["pace_hr_efficiency_m_per_min_per_bpm"])
                for item in items
                if item.workout_class == "easy"
                and _is_number(item.stream_features.get("pace_hr_efficiency_m_per_min_per_bpm"))
            ],
            "drift_values": drift,
            **_garmin_week(items),
        })
        week += timedelta(days=7)
    return rows


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _garmin_week(items: list[Activity]) -> dict[str, Any]:
    """Weekly Garmin aggregates; None when no run that week was matched to Garmin."""
    metrics = [item.garmin_metrics for item in items if getattr(item, "garmin_metrics", None)]
    loads = [m["training_load"] for m in metrics if _is_number(m.get("training_load"))]
    aerobic = [m["aerobic_training_effect"] for m in metrics if _is_number(m.get("aerobic_training_effect"))]
    zone_totals = [0.0] * 5
    for item in metrics:
        zones = item.get("hr_zone_seconds")
        if isinstance(zones, dict):
            for zone in range(5):
                seconds = zones.get(str(zone + 1))
                if _is_number(seconds) and seconds > 0:
                    zone_totals[zone] += float(seconds)
    zone_seconds = sum(zone_totals)
    dew_points = [
        m["weather"]["dew_point_c"]
        for m in metrics
        if isinstance(m.get("weather"), dict) and _is_number(m["weather"].get("dew_point_c"))
    ]
    return {
        "garmin_run_count": len(metrics),
        "garmin_training_load": sum(loads) if loads else None,
        "garmin_aerobic_te": mean(aerobic) if aerobic else None,
        "garmin_z2_share": (zone_totals[0] + zone_totals[1]) / zone_seconds * 100 if zone_seconds else None,
        "garmin_high_dew_point_runs": sum(value >= HIGH_DEW_POINT_C for value in dew_points) if dew_points else None,
    }


def build_training_context(weeks: list[dict[str, Any]], window: int = CONTEXT_WEEKS) -> dict[str, Any]:
    """The 5-point 6–12 week context used by activity analysis, plus Garmin weekly averages."""
    recent = weeks[-window:]
    weeks_with_runs = sum(1 for row in recent if row["run_count"])
    half = len(recent) // 2
    earlier, later = recent[:half], recent[half:]
    class_counts: dict[str, int] = {}
    for row in recent:
        for cls, count in row["class_counts"].items():
            class_counts[cls] = class_counts.get(cls, 0) + count
    total_km = sum(row["distance_km"] for row in recent)
    return {
        "window_weeks": len(recent),
        "weeks_with_runs": weeks_with_runs,
        "sufficient_for_trend": weeks_with_runs >= MIN_TREND_WEEKS,
        "run_count": sum(row["run_count"] for row in recent),
        "average_weekly_distance_km": round(total_km / len(recent), 1) if recent else None,
        "recent_4_week_distance_km": round(mean(row["distance_km"] for row in recent[-4:]), 1) if recent else None,
        "long_run_count": sum(row["long_run_count"] for row in recent),
        "workout_class_counts": dict(sorted(class_counts.items())),
        "weekly": [
            {
                "week_start": row["week_start"].isoformat(),
                "distance_km": round(row["distance_km"], 1),
                "run_count": row["run_count"],
                "long_run_count": row["long_run_count"],
                "garmin_training_load": _rounded(row["garmin_training_load"], 1),
            }
            for row in recent
        ],
        "easy_efficiency_trend": _half_trend(earlier, later, "easy_efficiency_values", 4),
        "steady_hr_drift_trend": _half_trend(earlier, later, "drift_values", 2),
        "garmin": {
            "weeks_with_data": sum(1 for row in recent if row["garmin_run_count"]),
            "matched_run_count": sum(row["garmin_run_count"] for row in recent),
            "average_weekly_training_load": _mean_of(recent, "garmin_training_load", 1),
            "average_aerobic_training_effect": _mean_of(recent, "garmin_aerobic_te", 2),
            "z1_z2_share_percent": _mean_of(recent, "garmin_z2_share", 1),
            "high_dew_point_runs": sum(row["garmin_high_dew_point_runs"] or 0 for row in recent),
        },
    }


def _rounded(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None


def _mean_of(rows: list[dict[str, Any]], key: str, digits: int) -> float | None:
    values = [row[key] for row in rows if row[key] is not None]
    return round(mean(values), digits) if values else None


def _half_trend(earlier: list[dict[str, Any]], later: list[dict[str, Any]], key: str, digits: int) -> dict[str, Any]:
    first = [value for row in earlier for value in row[key]]
    second = [value for row in later for value in row[key]]
    first_mean = round(mean(first), digits) if first else None
    second_mean = round(mean(second), digits) if second else None
    return {
        "sample_count": len(first) + len(second),
        "earlier_half_mean": first_mean,
        "later_half_mean": second_mean,
        "later_minus_earlier": round(second_mean - first_mean, digits) if first and second else None,
    }


def _week_datetime(day: date, zone: ZoneInfo):
    from datetime import datetime, time

    return datetime.combine(day, time.min, tzinfo=zone)


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        rank = (position + end) / 2 + 1
        for index in order[position : end + 1]:
            ranks[index] = rank
        position = end + 1
    return ranks


def _spearman(first: list[float], second: list[float]) -> float | None:
    if len(first) != len(second) or len(first) < 3:
        return None
    x = _ranks(first)
    y = _ranks(second)
    x_mean = mean(x)
    y_mean = mean(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y))
    denominator = math.sqrt(sum((a - x_mean) ** 2 for a in x) * sum((b - y_mean) ** 2 for b in y))
    return numerator / denominator if denominator else None


def _strength(value: float) -> str:
    if value >= 0.5:
        return "strong"
    if value >= 0.3:
        return "moderate"
    if value >= 0.2:
        return "weak"
    return "none"


def _factor_confidence(value: float, sample_size: int) -> str:
    if sample_size >= 20 and value >= 0.3:
        return "high"
    if sample_size >= 10 and value >= 0.2:
        return "medium"
    return "low"


def _direction_text(definition: FactorDefinition, correlation: float) -> str:
    if definition.direction == "lower":
        favorable = correlation < 0
        return "較低時，下一週效率通常較好" if favorable else "較高時，下一週效率通常較好"
    return "較高時，下一週效率通常較好" if correlation > 0 else "較低時，下一週效率通常較好"
