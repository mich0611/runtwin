from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.core.management.base import CommandError
from django.utils import timezone

from runtwin.athletes.models import AthleteProfile
from runtwin.reporting.periods import normalize_week_start


def get_athlete() -> AthleteProfile:
    athlete = AthleteProfile.objects.order_by("id").first()
    if not athlete:
        raise CommandError("找不到 AthleteProfile；請先執行 seed_athlete_profile。")
    return athlete


def resolve_week(value: str | None, athlete: AthleteProfile) -> date:
    if value:
        parsed = date.fromisoformat(value)
        if parsed.weekday() != 0:
            raise CommandError("--week 必須是星期一（YYYY-MM-DD）。")
        return parsed
    today = timezone.now().astimezone(ZoneInfo(athlete.timezone)).date()
    return normalize_week_start(today) - timedelta(days=7)
