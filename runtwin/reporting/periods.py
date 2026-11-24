from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def week_bounds(reference: date | datetime, timezone_name: str = "Asia/Taipei", previous_complete: bool = False) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone_name)
    if isinstance(reference, datetime):
        localized = reference.astimezone(zone) if reference.tzinfo else reference.replace(tzinfo=zone)
        local_date = localized.date()
    else:
        local_date = reference
    monday = local_date - timedelta(days=local_date.weekday())
    if previous_complete:
        monday -= timedelta(days=7)
    start = datetime.combine(monday, time.min, tzinfo=zone)
    end = datetime.combine(monday + timedelta(days=7), time.min, tzinfo=zone)
    return start, end


def normalize_week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())
