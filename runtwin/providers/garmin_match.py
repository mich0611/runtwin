from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

MAX_START_DIFF_SECONDS = 120
MAX_DISTANCE_DIFF_RATIO = 0.05


def parse_garmin_start_gmt(value: Any) -> datetime | None:
    """Parse Garmin's ``startTimeGMT`` ("YYYY-MM-DD HH:MM:SS", UTC) into an aware datetime."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace(" ", "T"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def match_garmin_activity(
    start_time: datetime,
    distance_m: float,
    candidates: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the Garmin activity closest in start time that matches within tolerances."""
    target = start_time.astimezone(timezone.utc)
    best: tuple[float, dict[str, Any]] | None = None
    for candidate in candidates:
        started = parse_garmin_start_gmt(candidate.get("startTimeGMT"))
        if started is None:
            continue
        diff = abs((started - target).total_seconds())
        if diff > MAX_START_DIFF_SECONDS:
            continue
        garmin_distance = candidate.get("distance")
        if distance_m > 0 and isinstance(garmin_distance, (int, float)):
            if abs(garmin_distance - distance_m) / distance_m > MAX_DISTANCE_DIFF_RATIO:
                continue
        if best is None or diff < best[0]:
            best = (diff, candidate)
    return best[1] if best else None
