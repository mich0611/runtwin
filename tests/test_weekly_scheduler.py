from datetime import date, datetime
from zoneinfo import ZoneInfo

from runtwin.web.management.commands.run_weekly_scheduler import generate_daily_reports, next_daily_run, report_weeks_for_day


def test_daily_report_updates_current_week_on_regular_day():
    assert report_weeks_for_day(date(2026, 9, 22)) == [date(2026, 9, 21)]


def test_monday_finalizes_previous_and_starts_current_week():
    assert report_weeks_for_day(date(2026, 9, 21)) == [date(2026, 9, 14), date(2026, 9, 21)]


def test_startup_catch_up_also_refreshes_previous_week():
    assert report_weeks_for_day(date(2026, 9, 22), include_previous=True) == [
        date(2026, 9, 14),
        date(2026, 9, 21),
    ]


def test_next_daily_run_uses_nine_am_taipei():
    zone = ZoneInfo("Asia/Taipei")

    before = next_daily_run(datetime(2026, 9, 22, 8, 30, tzinfo=zone))
    after = next_daily_run(datetime(2026, 9, 22, 17, 0, tzinfo=zone))

    assert before == datetime(2026, 9, 22, 9, 0, tzinfo=zone)
    assert after == datetime(2026, 9, 23, 9, 0, tzinfo=zone)


def test_daily_report_reconciles_before_generation(monkeypatch, settings):
    settings.STRAVA_RECONCILE_DAYS = 14
    calls = []
    monkeypatch.setattr("runtwin.web.management.commands.run_weekly_scheduler.close_old_connections", lambda: None)
    monkeypatch.setattr("runtwin.web.management.commands.run_weekly_scheduler.reconcile_recent_strava_runs", lambda **kwargs: calls.append(("reconcile", kwargs)))
    monkeypatch.setattr("runtwin.web.management.commands.run_weekly_scheduler.call_command", lambda name, **kwargs: calls.append((name, kwargs)))

    generate_daily_reports(date(2026, 9, 22))

    assert calls[0] == ("reconcile", {"days": 14, "limit": 100})
    assert calls[1] == ("generate_weekly_report", {"week": "2026-09-21", "export_prompt": True})
    assert calls[2] == ("generate_progress_narrative", {})
