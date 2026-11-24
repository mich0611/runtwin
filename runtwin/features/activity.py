from __future__ import annotations

import math
from statistics import mean, median, pstdev
from typing import Any

FEATURE_VERSION = "activity-features-v2"
STEADY_SPEED_CV_MAX = 0.06


def _valid_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _valid_hr(value: Any) -> bool:
    return _valid_number(value) and 30 <= value <= 230


def _linear_slope(values: list[float]) -> float | None:
    if len(values) < 3:
        return None
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = mean(values)
    denominator = sum((index - x_mean) ** 2 for index in range(n))
    if denominator == 0:
        return None
    return sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator


def calculate_stream_features(streams: dict[str, list[Any]], moving_time: int, distance_total: float) -> dict[str, Any]:
    time = streams.get("time", [])
    distance = streams.get("distance", [])
    hr = streams.get("heart_rate", [])
    velocity = streams.get("velocity_smooth", streams.get("velocity", []))
    moving = streams.get("moving", [])
    cadence = streams.get("cadence", [])
    required = [values for values in (time, distance, velocity) if values]
    common = min((len(values) for values in required), default=0)
    if len(required) < 3 or common < 4:
        return {"calculation_version": FEATURE_VERSION, "status": "insufficient_data"}

    indices = [index for index in range(common) if (not moving or index >= len(moving) or bool(moving[index])) and _valid_number(velocity[index]) and velocity[index] > 0]
    speeds = [float(velocity[index]) for index in indices]
    hrs = [float(hr[index]) for index in indices if index < len(hr) and _valid_hr(hr[index])]
    if not speeds:
        return {"calculation_version": FEATURE_VERSION, "status": "insufficient_data"}

    speed_median = median(speeds)
    pace_seconds = 1000 / speed_median if speed_median else None
    hr_median = median(hrs) if hrs else None
    valid_cadence = [float(cadence[index]) for index in indices if index < len(cadence) and _valid_number(cadence[index]) and cadence[index] > 0]

    # One-minute moving windows give robust pattern features at either 1 Hz or reduced snapshots.
    windows: list[dict[str, float]] = []
    start_position = 0
    while start_position < len(indices):
        start_index = indices[start_position]
        start_time = time[start_index]
        end_position = start_position
        while end_position + 1 < len(indices) and time[indices[end_position + 1]] - start_time < 60:
            end_position += 1
        window_indices = indices[start_position : end_position + 1]
        if window_indices and time[window_indices[-1]] - start_time >= 30:
            window_speeds = [float(velocity[index]) for index in window_indices]
            window_hr = [float(hr[index]) for index in window_indices if index < len(hr) and _valid_hr(hr[index])]
            windows.append({
                "speed": mean(window_speeds),
                "hr": mean(window_hr) if window_hr else 0.0,
                "time": float(start_time),
            })
        start_position = end_position + 1

    # MCP exports may intentionally be downsampled. Individual samples remain useful
    # for coarse pattern recognition, but downstream confidence stays conservative.
    if len(windows) < 4 and len(indices) >= 4:
        windows = [
            {"speed": float(velocity[index]), "hr": float(hr[index]) if index < len(hr) and _valid_hr(hr[index]) else 0.0, "time": float(time[index])}
            for index in indices
        ]

    window_speeds = [window["speed"] for window in windows]
    fast_cutoff = max(speed_median * 1.10, 3.2)
    easy_cutoff = speed_median * 0.82
    fast_flags = [value >= fast_cutoff for value in window_speeds]
    recovery_flags = [value <= easy_cutoff for value in window_speeds]
    transitions = sum(first != second for first, second in zip(fast_flags, fast_flags[1:]))
    fast_blocks = sum(flag and (index == 0 or not fast_flags[index - 1]) for index, flag in enumerate(fast_flags))
    has_repeated_fast_recovery = fast_blocks >= 3 and sum(recovery_flags) >= 2

    half = len(window_speeds) // 2
    progression_ratio = None
    if half >= 2:
        first_speed = mean(window_speeds[:half])
        second_speed = mean(window_speeds[-half:])
        progression_ratio = second_speed / first_speed if first_speed else None

    stable = False
    hr_drift_percent = None
    efficiency = None
    if moving_time >= 30 * 60 and len(windows) >= 8 and hrs:
        trimmed = windows[1:-1] if len(windows) > 10 else windows
        speeds_for_stability = [item["speed"] for item in trimmed]
        if speeds_for_stability:
            # Coefficient of variation tolerates a few stop-and-go minutes (traffic lights,
            # GPS spikes) that made the old max-min range reject otherwise steady runs.
            coefficient = pstdev(speeds_for_stability) / mean(speeds_for_stability)
            stable = coefficient <= STEADY_SPEED_CV_MAX
        if stable:
            midpoint = len(trimmed) // 2
            first = [item for item in trimmed[:midpoint] if item["hr"] > 0]
            second = [item for item in trimmed[midpoint:] if item["hr"] > 0]
            if len(first) >= 2 and len(second) >= 2:
                ratio_first = mean(item["speed"] / item["hr"] for item in first)
                ratio_second = mean(item["speed"] / item["hr"] for item in second)
                hr_drift_percent = (ratio_first / ratio_second - 1) * 100 if ratio_second else None
        paired = [(float(velocity[index]), float(hr[index])) for index in indices if index < len(hr) and _valid_hr(hr[index])]
        if paired:
            efficiency = mean(speed / heart_rate for speed, heart_rate in paired) * 60

    return {
        "status": "ok",
        "sample_count": common,
        "median_speed_mps": round(speed_median, 4),
        "median_pace_seconds_per_km": round(pace_seconds, 2) if pace_seconds else None,
        "median_hr_bpm": round(hr_median, 2) if hr_median else None,
        "median_cadence_spm": round(median(valid_cadence) * 2, 2) if valid_cadence else None,
        "minute_window_count": len(windows),
        "speed_variability": round((max(window_speeds) - min(window_speeds)) / mean(window_speeds), 4) if window_speeds else None,
        "fast_block_count": fast_blocks,
        "speed_transition_count": transitions,
        "has_repeated_fast_recovery": has_repeated_fast_recovery,
        "progression_ratio": round(progression_ratio, 4) if progression_ratio else None,
        "steady_run": stable,
        "hr_drift_percent": round(hr_drift_percent, 2) if hr_drift_percent is not None else None,
        "pace_hr_efficiency_m_per_min_per_bpm": round(efficiency, 4) if efficiency is not None else None,
        "calculation_version": FEATURE_VERSION,
    }
