from io import StringIO
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from runtwin.activities.models import Activity


@pytest.mark.django_db
def test_backfill_dry_run_lists_only_missing_or_unpublished(monkeypatch):
    published = Activity.objects.create(
        strava_activity_id="100",
        name="Done",
        start_time=timezone.now(),
        sport_type="Run",
        distance=5000,
        moving_time=1500,
        elapsed_time=1500,
        analysis="done",
        analysis_source="ai:anthropic",
        analysis_published_at=timezone.now(),
    )
    assert published.analysis_published_at is not None
    Activity.objects.create(
        strava_activity_id="200",
        name="Missing",
        start_time=timezone.now(),
        sport_type="Run",
        distance=5000,
        moving_time=1500,
        elapsed_time=1500,
        analysis="",
    )
    payloads = [
        {"id": 100, "name": "Done", "sport_type": "Run", "start_date": "2026-09-01T00:00:00Z"},
        {"id": 200, "name": "Missing", "sport_type": "Run", "start_date": "2026-09-02T00:00:00Z"},
        {"id": 300, "name": "Ride", "sport_type": "Ride", "start_date": "2026-09-03T00:00:00Z"},
    ]
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.StravaWriteClient.from_settings", lambda: Mock())
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.StravaApiProvider.list_activities", lambda self, start=None, end=None: iter(payloads))
    process = Mock(side_effect=AssertionError("dry run must not process"))
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.process_strava_activity", process)
    output = StringIO()

    call_command("backfill_activity_analyses", since="2026-09-01", until="2026-09-30", dry_run=True, stdout=output)

    assert "候選活動：1 筆" in output.getvalue()
    assert "200 Missing" in output.getvalue()
    assert "100 Done" not in output.getvalue()
    process.assert_not_called()


@pytest.mark.django_db
def test_backfill_retry_fallback_resets_and_processes(monkeypatch):
    activity = Activity.objects.create(
        strava_activity_id="200",
        name="Fallback",
        start_time=timezone.now(),
        sport_type="Run",
        distance=5000,
        moving_time=1500,
        elapsed_time=1500,
        analysis="fallback",
        analysis_source="deterministic-fallback",
        analysis_published_at=timezone.now(),
    )
    payload = {"id": 200, "name": "Fallback", "sport_type": "Run", "start_date": "2026-09-02T00:00:00Z"}
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.StravaWriteClient.from_settings", lambda: Mock())
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.StravaApiProvider.list_activities", lambda self, start=None, end=None: iter([payload]))

    def process(activity_id, client=None, garmin_provider=None):
        activity.refresh_from_db()
        assert activity.analysis_published_at is None
        return "complete"

    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.process_strava_activity", process)

    call_command("backfill_activity_analyses", since="2026-09-01", retry_fallback=True, pause_seconds=0, batch_pause_seconds=0)


@pytest.mark.django_db
def test_backfill_clears_interrupted_claim_before_retry(monkeypatch):
    activity = Activity.objects.create(
        strava_activity_id="200",
        name="Interrupted",
        start_time=timezone.now(),
        sport_type="Run",
        distance=5000,
        moving_time=1500,
        elapsed_time=1500,
        analysis="local",
        analysis_source="deterministic",
        analysis_claimed_at=timezone.now(),
    )
    payload = {"id": 200, "name": "Interrupted", "sport_type": "Run", "start_date": "2026-09-02T00:00:00Z"}
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.StravaWriteClient.from_settings", lambda: Mock())
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.StravaApiProvider.list_activities", lambda self, start=None, end=None: iter([payload]))

    def process(activity_id, client=None, garmin_provider=None):
        activity.refresh_from_db()
        assert activity.analysis_claimed_at is None
        return "complete"

    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.process_strava_activity", process)

    call_command("backfill_activity_analyses", since="2026-09-01", pause_seconds=0, batch_pause_seconds=0)


@pytest.mark.django_db
def test_backfill_reuses_one_garmin_provider_for_every_activity(monkeypatch):
    payloads = [
        {"id": 200, "name": "A", "sport_type": "Run", "start_date": "2026-09-02T00:00:00Z"},
        {"id": 300, "name": "B", "sport_type": "Run", "start_date": "2026-09-03T00:00:00Z"},
    ]
    garmin = object()
    factory = Mock(return_value=garmin)
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.StravaWriteClient.from_settings", lambda: Mock())
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.StravaApiProvider.list_activities", lambda self, start=None, end=None: iter(payloads))
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.garmin_provider_from_settings", factory)
    process = Mock(return_value="complete")
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.process_strava_activity", process)

    call_command("backfill_activity_analyses", since="2026-09-01", until="2026-09-30", pause_seconds=0, batch_pause_seconds=0)

    factory.assert_called_once_with()
    assert [call.args[0] for call in process.call_args_list] == ["200", "300"]
    assert all(call.kwargs["garmin_provider"] is garmin for call in process.call_args_list)


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"since": "2026-13-01"}, "YYYY-MM-DD"),
        ({"since": "2026-09-10", "until": "2026-09-01"}, "--until"),
    ],
)
def test_backfill_rejects_invalid_date_range(options, message):
    with pytest.raises(CommandError, match=message):
        call_command("backfill_activity_analyses", **options)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("batch_size", "batch_pause_seconds", "pause_seconds", "sleeps"),
    [
        (1, 5, 0.5, [5, 5]),
        (1, 0, 0.5, [0.5, 0.5]),
        (2, 5, 0, [5]),
    ],
)
def test_backfill_limit_failures_and_pauses(monkeypatch, batch_size, batch_pause_seconds, pause_seconds, sleeps):
    payloads = [
        {"id": 100 + day, "name": f"Run {day}", "sport_type": "Run", "start_date": f"2026-09-0{day}T00:00:00Z"}
        for day in range(1, 5)
    ]
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.StravaWriteClient.from_settings", lambda: Mock())
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.StravaApiProvider.list_activities", lambda self, start=None, end=None: iter(payloads))
    process = Mock(side_effect=[RuntimeError("Strava down"), "complete", "complete"])
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.process_strava_activity", process)
    sleep = Mock()
    monkeypatch.setattr("runtwin.web.management.commands.backfill_activity_analyses.time_module.sleep", sleep)
    stdout, stderr = StringIO(), StringIO()

    call_command(
        "backfill_activity_analyses",
        since="2026-09-01",
        until="2026-09-30",
        limit=3,
        batch_size=batch_size,
        batch_pause_seconds=batch_pause_seconds,
        pause_seconds=pause_seconds,
        stdout=stdout,
        stderr=stderr,
    )

    assert [call.args[0] for call in process.call_args_list] == ["101", "102", "103"]
    assert "[1/3] 101 failed: RuntimeError: Strava down" in stderr.getvalue()
    assert "'complete': 2" in stdout.getvalue()
    assert "'failed': 1" in stdout.getvalue()
    assert [call.args[0] for call in sleep.call_args_list] == sleeps
