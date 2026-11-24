from __future__ import annotations

import math
from typing import Any


def _haversine_m(first: list[float], second: list[float]) -> float:
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_000 * 2 * math.asin(math.sqrt(value))

QUALITY_VERSION = "quality-v1"


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def assess_stream_quality(streams: dict[str, list[Any]], moving_time: int, elapsed_time: int) -> dict[str, Any]:
    time = streams.get("time", [])
    distance = streams.get("distance", [])
    heart_rate = streams.get("heart_rate", [])
    velocity = streams.get("velocity_smooth", streams.get("velocity", []))
    altitude = streams.get("altitude", [])
    moving = streams.get("moving", [])
    gps = streams.get("location", streams.get("gps", []))
    lengths = [len(values) for values in streams.values() if isinstance(values, list) and values]
    sample_count = max(lengths, default=0)
    issues: list[dict[str, Any]] = []

    if sample_count == 0:
        issues.append({"code": "missing_streams", "severity": "error", "message": "沒有 activity stream。"})
    unequal = {len(values) for values in streams.values() if isinstance(values, list) and values}
    if len(unequal) > 1:
        issues.append({"code": "stream_length_mismatch", "severity": "error", "message": "Stream 長度不一致。"})
    if time and any(not _finite_number(value) for value in time):
        issues.append({"code": "invalid_time", "severity": "error", "message": "時間序列含非數值。"})
    if time and any(b <= a for a, b in zip(time, time[1:])):
        issues.append({"code": "non_monotonic_time", "severity": "error", "message": "時間序列並非嚴格遞增。"})
    if distance and any(not _finite_number(value) or value < 0 for value in distance):
        issues.append({"code": "invalid_distance", "severity": "error", "message": "距離序列含無效值。"})
    if distance and any(b < a for a, b in zip(distance, distance[1:])):
        issues.append({"code": "distance_reversal", "severity": "warning", "message": "累積距離曾倒退。"})
    if gps:
        invalid_gps = [point for point in gps if not isinstance(point, list) or len(point) != 2 or not all(_finite_number(value) for value in point) or not (-90 <= point[0] <= 90 and -180 <= point[1] <= 180)]
        if invalid_gps:
            issues.append({"code": "invalid_gps", "severity": "warning", "message": f"有 {len(invalid_gps)} 筆 GPS 座標無效。"})
        elif time and len(gps) == len(time):
            gps_jumps = 0
            for index, (first, second) in enumerate(zip(gps, gps[1:]), start=1):
                delta_t = time[index] - time[index - 1]
                if delta_t > 0 and _haversine_m(first, second) / delta_t > 15:
                    gps_jumps += 1
            if gps_jumps:
                issues.append({"code": "gps_spikes", "severity": "warning", "message": f"偵測到 {gps_jumps} 個 GPS 跳點。"})

    valid_hr = [value for value in heart_rate if _finite_number(value) and 30 <= value <= 230]
    invalid_hr = [value for value in heart_rate if not _finite_number(value) or not 30 <= value <= 230]
    if not heart_rate:
        issues.append({"code": "missing_hr", "severity": "info", "message": "缺少心率 stream。"})
    elif invalid_hr:
        issues.append({"code": "invalid_hr", "severity": "warning", "message": f"有 {len(invalid_hr)} 筆心率超出 30–230 bpm。"})

    speed_jumps = 0
    if velocity:
        for first, second in zip(velocity, velocity[1:]):
            if _finite_number(first) and _finite_number(second) and (second > 12 or abs(second - first) > 6):
                speed_jumps += 1
        if speed_jumps:
            issues.append({"code": "speed_spikes", "severity": "warning", "message": f"偵測到 {speed_jumps} 個速度跳點。"})

    stopped_seconds = max(0, elapsed_time - moving_time)
    stopped_ratio = stopped_seconds / elapsed_time if elapsed_time else 0
    if stopped_seconds >= 180 or stopped_ratio >= 0.1:
        issues.append({"code": "long_stops", "severity": "warning", "message": f"停等約 {stopped_seconds} 秒（{stopped_ratio:.0%}）。"})

    penalties = {"error": 25, "warning": 10, "info": 3}
    score = max(0, 100 - sum(penalties[item["severity"]] for item in issues))
    expected_seconds = max(moving_time, 1)
    sampling_coverage = min(1.0, sample_count / expected_seconds) if sample_count else 0.0
    hr_coverage = len(valid_hr) / sample_count if sample_count else 0.0

    return {
        "score": float(score),
        "issues": issues,
        "sample_count": sample_count,
        "sampling_coverage": round(sampling_coverage, 4),
        "hr_coverage": round(hr_coverage, 4),
        "has_hr_stream": bool(valid_hr),
        "has_pace_stream": bool(velocity or (time and distance)),
        "has_altitude_stream": bool(altitude),
        "has_gps_stream": bool(gps),
        "long_stop_ratio": round(stopped_ratio, 4),
        "speed_jump_count": speed_jumps,
        "quality_version": QUALITY_VERSION,
    }
