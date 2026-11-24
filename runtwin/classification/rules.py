from __future__ import annotations

import re
from typing import Any

CLASSIFIER_VERSION = "rules-v4"
QUALITY_CLASSES = {"tempo_threshold", "tempo", "threshold", "fartlek", "interval", "progression", "race"}
# Easy pace band where pace alone is ambiguous; Strava stream heart rate decides instead.
EASY_HR_PACE_MIN_SECONDS = 270
EASY_HR_PACE_MAX_SECONDS = 285
EASY_HR_MAX_RATIO_OF_TEMPO = 0.9


def _full_distance_personal_bests(summary: dict[str, Any] | None, activity_distance_m: float) -> list[str]:
    summary = summary or {}
    efforts = summary.get("best_efforts")
    if not isinstance(efforts, list) or activity_distance_m <= 0:
        return []

    names: list[str] = []
    for effort in efforts:
        if not isinstance(effort, dict) or effort.get("pr_rank") != 1:
            continue
        try:
            effort_distance = float(effort.get("distance") or 0)
        except (TypeError, ValueError):
            continue
        if effort_distance >= 3000 and effort_distance >= activity_distance_m * 0.9:
            names.append(str(effort.get("name") or "best effort"))
    return names


def classify_activity(
    *,
    name: str,
    description: str,
    distance_m: float,
    moving_time_s: int,
    features: dict[str, Any],
    recent_distance_percentile: float | None = None,
    summary: dict[str, Any] | None = None,
    tempo_hr_low: float | None = None,
) -> dict[str, Any]:
    text = f"{name} {description}".lower()
    reasons: list[str] = []
    feature_status = features.get("status") == "ok"
    pace = features.get("median_pace_seconds_per_km")
    variability = features.get("speed_variability")
    progression = features.get("progression_ratio")
    repeated = bool(features.get("has_repeated_fast_recovery"))
    fast_blocks = int(features.get("fast_block_count") or 0)

    race_name = bool(re.search(r"\b(race|marathon|half.?marathon|10k race|5k race)\b|馬拉松|路跑賽|競賽", text))
    interval_name = bool(re.search(r"interval|repetition|\d+\s*[x×]\s*\d+|間歇", text))
    fartlek_name = bool(re.search(r"fartlek|法特雷克|變速跑", text))
    progression_name = bool(re.search(r"progressi|漸速|negative split", text))
    threshold_name = bool(re.search(r"threshold|閾值|乳酸閾", text))
    tempo_name = bool(re.search(r"tempo|節奏", text))
    recovery_name = bool(re.search(r"recover|恢復", text))
    easy_name = bool(re.search(r"easy|base|輕鬆|有氧", text))
    long_name = bool(re.search(r"long run|長跑|lsd", text))
    personal_bests = _full_distance_personal_bests(summary, distance_m)

    if personal_bests and feature_status:
        reasons.extend([f"Strava 標示個人最佳：{', '.join(personal_bests)}", "完整活動 stream 支持高品質測驗／競賽判定"])
        return _result("race", 0.95, reasons)
    if race_name and feature_status and (moving_time_s >= 15 * 60 or distance_m >= 5000):
        reasons.extend(["活動名稱具比賽語意", "活動距離或時間足以支持比賽分類"])
        return _result("race", 0.88, reasons)
    if repeated and fartlek_name:
        reasons.extend([f"偵測到 {fast_blocks} 個速度變化區段", "名稱具 Fartlek／法特雷克語意"])
        return _result("fartlek", 0.9, reasons)
    if repeated and (interval_name or fast_blocks >= 4):
        reasons.extend([f"偵測到 {fast_blocks} 個高速區段", "高速與恢復區段重複出現"])
        if interval_name:
            reasons.append("名稱提供間歇語意作為輔助證據")
        return _result("interval", 0.9 if interval_name else 0.82, reasons)
    if feature_status and progression is not None and progression >= 1.10 and moving_time_s >= 30 * 60:
        reasons.extend([f"後半速度為前半的 {progression:.2f} 倍", "持續時間足以形成漸速刺激"])
        if progression_name:
            reasons.append("名稱與 stream 特徵一致")
        return _result("progression", 0.86 if progression_name else 0.78, reasons)
    if feature_status and threshold_name and pace and moving_time_s >= 20 * 60 and not repeated and (variability is None or variability <= 0.35):
        reasons.extend(["名稱具 Threshold／閾值語意", "stream 顯示非重複間歇且具持續性"])
        return _result("threshold", 0.8, reasons)
    if feature_status and tempo_name and pace and moving_time_s >= 20 * 60 and not repeated and (variability is None or variability <= 0.35):
        reasons.extend(["名稱具 Tempo／節奏語意", "stream 顯示非重複間歇且具持續性"])
        return _result("tempo", 0.8, reasons)
    if feature_status and not repeated and moving_time_s >= 20 * 60 and pace and pace <= 270 and (variability is None or variability <= 0.22):
        reasons.extend(["有持續穩定的較快配速區段", "未偵測到反覆恢復型態"])
        return _result("tempo_threshold", 0.68, reasons)
    is_long = distance_m >= 16000 or moving_time_s >= 90 * 60 or (recent_distance_percentile is not None and recent_distance_percentile >= 0.9 and distance_m >= 12000)
    if is_long:
        reasons.append("距離、時間或近期距離百分位符合長跑條件")
        if long_name:
            reasons.append("名稱與距離特徵一致")
        return _result("long", 0.82 if long_name else 0.72, reasons)
    if recovery_name and feature_status and pace and pace >= 300:
        reasons.extend(["名稱具恢復語意", "stream 配速未呈現品質課型態"])
        return _result("recovery", 0.72, reasons)
    if easy_name and feature_status and not repeated and (pace is None or pace >= 270):
        reasons.extend(["名稱具 Easy/Base 語意", "stream 未呈現品質課型態"])
        return _result("easy", 0.72, reasons)
    if feature_status and not repeated and pace and pace >= EASY_HR_PACE_MAX_SECONDS:
        reasons.append("配速穩定且未偵測到品質課型態")
        return _result("easy", 0.62, reasons)
    easy_hr_ceiling = _easy_hr_ceiling(tempo_hr_low)
    median_hr = features.get("median_hr_bpm")
    if (
        feature_status
        and not repeated
        and features.get("steady_run")
        and pace
        and EASY_HR_PACE_MIN_SECONDS < pace < EASY_HR_PACE_MAX_SECONDS
        and easy_hr_ceiling is not None
        and _is_number(median_hr)
        and median_hr <= easy_hr_ceiling
    ):
        reasons.extend([
            f"配速 {pace:.0f} 秒／公里介於 Easy 與節奏之間，改以心率判斷",
            f"中位心率 {median_hr:.0f} bpm ≤ 節奏心率下限的 {EASY_HR_MAX_RATIO_OF_TEMPO:.0%}（{easy_hr_ceiling:.0f} bpm）",
            "配速穩定且未偵測到品質課型態",
        ])
        return _result("easy", 0.6, reasons)
    reasons.append("名稱與 stream 特徵不足以可靠分類")
    return _result("unknown", 0.3, reasons)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _easy_hr_ceiling(tempo_hr_low: Any) -> float | None:
    if not _is_number(tempo_hr_low) or tempo_hr_low <= 0:
        return None
    return float(tempo_hr_low) * EASY_HR_MAX_RATIO_OF_TEMPO


def _result(workout_class: str, confidence: float, reasons: list[str]) -> dict[str, Any]:
    return {"workout_class": workout_class, "confidence": confidence, "reasons": reasons, "classifier_version": CLASSIFIER_VERSION}
