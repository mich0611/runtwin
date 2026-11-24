from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from runtwin.activities.webhook import reconcile_recent_strava_runs
from runtwin.reporting.periods import normalize_week_start

REPORT_TIMEZONE = "Asia/Taipei"
REPORT_HOUR = 9
REPORT_MINUTE = 0


def report_weeks_for_day(day: date, *, include_previous: bool = False) -> list[date]:
    current = normalize_week_start(day)
    if include_previous or day.weekday() == 0:
        return [current - timedelta(days=7), current]
    return [current]


def next_daily_run(now: datetime) -> datetime:
    target = now.replace(hour=REPORT_HOUR, minute=REPORT_MINUTE, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def generate_daily_reports(day: date, *, include_previous: bool = False) -> None:
    close_old_connections()
    try:
        reconcile_recent_strava_runs(days=settings.STRAVA_RECONCILE_DAYS, limit=100)
    except Exception:
        # Weekly facts can still be refreshed from local data when Strava is unavailable.
        pass
    for week in report_weeks_for_day(day, include_previous=include_previous):
        call_command("generate_weekly_report", week=week.isoformat(), export_prompt=True)
    call_command("generate_progress_narrative")


class Command(BaseCommand):
    help = "常駐排程器：每日 09:00 Asia/Taipei 更新當週週報；週一同時結算上一週。"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="立即更新當週與上一完整週後結束，供測試或外部排程使用。")

    def handle(self, *args, **options):
        zone = ZoneInfo(REPORT_TIMEZONE)
        if options["once"]:
            generate_daily_reports(datetime.now(zone).date(), include_previous=True)
            return

        self.stdout.write("RunTwin scheduler started; target daily 09:00 Asia/Taipei.")
        # Startup catch-up includes the previous week in case Monday's final run was missed.
        try:
            generate_daily_reports(datetime.now(zone).date(), include_previous=True)
        except Exception as exc:
            self.stderr.write(f"startup catch-up failed: {type(exc).__name__}: {exc}")
        while True:
            now = datetime.now(zone)
            target = next_daily_run(now)
            time.sleep(max(1, (target - now).total_seconds()))
            try:
                generate_daily_reports(target.date())
            except Exception as exc:  # scheduler must remain retryable on the next run
                self.stderr.write(f"daily generation failed: {type(exc).__name__}: {exc}")
