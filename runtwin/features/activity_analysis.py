from __future__ import annotations

from statistics import mean
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from runtwin.activities.models import Activity

ANALYSIS_VERSION = "activity-analysis-v2"
QUALITY_WORKOUTS = {"tempo_threshold", "tempo", "threshold", "fartlek", "interval", "progression", "race"}
HIGH_DEW_POINT_C = 18.0
MIN_RATING_QUALITY_SCORE = 70
STIMULUS_BY_LABEL = {
    "RECOVERY": "恢復",
    "AEROBIC_BASE": "有氧基礎",
    "TEMPO": "閾值",
    "LACTATE_THRESHOLD": "閾值",
    "VO2MAX": "無氧",
    "ANAEROBIC_CAPACITY": "無氧",
    "SPEED": "無氧",
}
STIMULUS_BY_CLASS = {
    "easy": "有氧基礎",
    "recovery": "有氧基礎",
    "long": "有氧基礎",
    "tempo_threshold": "閾值",
    "tempo": "閾值",
    "threshold": "閾值",
    "progression": "閾值",
    "fartlek": "無氧",
    "interval": "無氧",
}


def _pace(value: float | None) -> str:
    if value is None or value <= 0:
        return "資料不足"
    total_seconds = round(value)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}/km"


def _duration(value: int) -> str:
    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def _summary_value(summary: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = summary.get(key)
        if value is not None:
            return value
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def high_dew_point(metrics: dict[str, Any] | None) -> float | None:
    """Return the Garmin dew point when it is high enough to slow pace or raise heart rate."""
    weather = (metrics or {}).get("weather")
    dew_point = weather.get("dew_point_c") if isinstance(weather, dict) else None
    if _is_number(dew_point) and dew_point >= HIGH_DEW_POINT_C:
        return float(dew_point)
    return None


def build_activity_analysis(activity: Activity, history: dict[str, Any] | None = None) -> str:
    """Create a concise, deterministic analysis from persisted activity metrics."""
    distance_km = activity.distance / 1000
    features = activity.stream_features or {}
    summary = activity.raw_summary or {}
    garmin = activity.garmin_metrics or {}
    lines = [
        "🏃 活動判讀",
        (
            f"本次判定為{activity.get_workout_class_display()}，完成 {distance_km:.2f} km，"
            f"移動時間 {_duration(activity.moving_time)}，平均配速 {_pace(activity.average_pace)}。"
        ),
    ]

    physiological: list[str] = []
    if activity.average_hr is not None:
        physiological.append(f"平均心率 {activity.average_hr:.0f} bpm")
    if activity.max_hr is not None:
        physiological.append(f"最高心率 {activity.max_hr:.0f} bpm")
    cadence = features.get("median_cadence_spm")
    if isinstance(cadence, (int, float)):
        physiological.append(f"中位步頻 {cadence:.0f} spm")
    watts = _summary_value(summary, "average_watts", "avg_watts")
    if isinstance(watts, (int, float)):
        physiological.append(f"平均功率 {watts:.0f} W")
    if physiological:
        lines.append("；".join(physiological) + "。")
    lines.extend(["⭐ 整體評比", _overall_rating(activity, features)])

    observations: list[str] = []
    if features.get("has_repeated_fast_recovery"):
        observations.append("速度變化呈現重複快跑與恢復段，符合間歇型態")
    progression_ratio = features.get("progression_ratio")
    if isinstance(progression_ratio, (int, float)):
        if progression_ratio >= 1.05:
            observations.append(f"後半速度約比前半高 {(progression_ratio - 1) * 100:.0f}%，有明顯漸速")
        elif progression_ratio <= 0.95:
            observations.append(f"後半速度約比前半低 {(1 - progression_ratio) * 100:.0f}%，可留意疲勞或路況影響")
    drift = features.get("hr_drift_percent")
    if isinstance(drift, (int, float)):
        if abs(drift) <= 5:
            observations.append(f"穩定跑心率漂移 {drift:+.1f}%，有氧輸出大致穩定")
        elif drift > 5:
            observations.append(f"穩定跑心率漂移 {drift:+.1f}%，可能受疲勞、補水或環境影響")
    dew_point = high_dew_point(garmin)
    if dew_point is not None:
        observations.append(f"露點 {dew_point:.1f}°C 偏高，配速偏慢或心率偏高可能是濕熱天氣造成，不代表體能下降")
    lines.append("📊 數據觀察")
    lines.append("；".join(observations) + "。" if observations else "可用 stream 證據不足，暫不推論配速變化或心率漂移。")

    lines.extend(["🎯 這堂課練了什麼", _stimulus_summary(activity.workout_class, garmin)])
    lines.extend(["🌱 恢復與下一步", _recovery_recommendation(activity.workout_class, activity.moving_time)])
    lines.extend(["🧭 下一步", _next_steps(history)])
    if activity.quality_issues:
        lines.append("⚠️ 資料提醒：部分 stream 資料不完整或品質不足，以上判讀應保守解讀。")
    return "\n".join(lines)


def _overall_rating(activity: Activity, features: dict[str, Any]) -> str:
    # One warning (e.g. a single GPS spike) costs 10 points; only an error or several warnings fall below this.
    if activity.quality_issues and getattr(activity, "data_quality_score", 0) < MIN_RATING_QUALITY_SCORE:
        return "資料品質不足，完成品質只能保守評估，請以主觀感受為準。"
    if activity.workout_class == "unknown":
        return "分類證據有限，無法判斷是否達成預定目的，先以完成訓練量看待。"
    drift = features.get("hr_drift_percent")
    if features.get("steady_run") and _is_number(drift) and abs(drift) <= 5:
        return f"以{activity.get_workout_class_display()}來看，配速穩定且心率漂移小，完成品質良好。"
    return f"以{activity.get_workout_class_display()}來看已完成預定訓練量；缺少穩定度證據，品質評估保守。"


def _stimulus_summary(workout_class: str, garmin: dict[str, Any]) -> str:
    aerobic = garmin.get("aerobic_training_effect")
    anaerobic = garmin.get("anaerobic_training_effect")
    if _is_number(aerobic) and _is_number(anaerobic):
        kind = STIMULUS_BY_LABEL.get(str(garmin.get("training_effect_label") or "").upper())
        if kind is None:
            kind = "無氧" if anaerobic >= 3 else "閾值" if aerobic >= 4 else "有氧基礎"
        text = f"Garmin 訓練效果有氧 {aerobic:.1f}、無氧 {anaerobic:.1f}，主要刺激偏{kind}"
    elif workout_class in STIMULUS_BY_CLASS:
        text = f"沒有 Garmin 訓練效果資料，依分類推估主要刺激偏{STIMULUS_BY_CLASS[workout_class]}"
    else:
        text = "沒有 Garmin 訓練效果資料，分類證據也有限，暫不判斷刺激類型"
    zones = garmin.get("hr_zone_seconds")
    if isinstance(zones, dict):
        valid = {zone: seconds for zone, seconds in zones.items() if _is_number(seconds) and seconds > 0}
        if valid:
            zone, seconds = max(valid.items(), key=lambda item: item[1])
            text += f"；心率以 Z{zone} 為主（約 {seconds / sum(valid.values()) * 100:.0f}%）"
    return text + "。"


def _next_steps(history: dict[str, Any] | None) -> str:
    weekly = [week["distance_km"] for week in (history or {}).get("weekly", [])]
    if not history or not history.get("sufficient_for_trend") or len(weekly) <= 4:
        return "近 6–12 週的訓練紀錄不足以看出趨勢，先維持目前的訓練規律，累積更多紀錄後再調整。"
    recent_average = mean(weekly[-4:])
    earlier_average = mean(weekly[:-4])
    if recent_average > earlier_average * 1.1:
        text = f"近 4 週平均週跑量 {recent_average:.1f} km，高於前段的 {earlier_average:.1f} km，接下來 1–2 週先持平，不再加量"
    elif recent_average < earlier_average * 0.9:
        text = f"近 4 週平均週跑量 {recent_average:.1f} km，低於前段的 {earlier_average:.1f} km，可逐步回升，每週增幅不超過 10%"
    else:
        text = f"近 4 週平均週跑量 {recent_average:.1f} km，與前段相近，可維持目前的訓練結構"
    if not history.get("long_run_count"):
        text += "；這段期間沒有長跑，可每 1–2 週安排一次輕鬆長跑"
    return text + "。"


def _recovery_recommendation(workout_class: str, moving_time: int) -> str:
    if workout_class == "race":
        return "本次屬高負荷刺激，接下來 48–72 小時以休息或非常輕鬆跑為主，再依腿部與睡眠狀態恢復品質課。"
    if workout_class in QUALITY_WORKOUTS:
        return "隔天安排休息或 30–50 分鐘非常輕鬆跑，下一堂品質課至少間隔 48 小時；若腿重或睡眠不佳則再順延。"
    if workout_class == "long" or moving_time >= 90 * 60:
        return "長距離後隔天以休息或短恢復跑為主，下一堂品質課建議間隔 48–72 小時。"
    if workout_class == "recovery":
        return "維持低強度即可；若跑後仍感到沉重，下一天休息，不需要追加速度訓練。"
    if workout_class == "easy":
        return "這次負荷適合作為有氧累積；若隔天精神、睡眠與腿部狀態正常，可照原計畫訓練。"
    return "分類證據有限；先依主觀疲勞與腿部狀態安排休息或輕鬆跑，不因單次數據追加強度。"
