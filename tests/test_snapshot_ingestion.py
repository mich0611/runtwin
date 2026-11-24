from pathlib import Path

import pytest

from runtwin.activities.models import Activity, ActivityStream, DataSyncRun
from runtwin.ingestion.service import import_provider
from runtwin.providers.snapshot import SnapshotProvider
from runtwin.providers.strava_publish import merge_analysis_into_description


@pytest.mark.django_db
def test_snapshot_upsert_is_idempotent():
    path = Path(__file__).parent.parent / "fixtures" / "anonymous_mcp_snapshot.json"
    first = import_provider(SnapshotProvider(path))
    second = import_provider(SnapshotProvider(path))
    assert first["created"] == 7
    assert second["created"] == 0
    assert second["updated"] == 7
    assert Activity.objects.count() == 7
    assert all(Activity.objects.values_list("analysis", flat=True))
    classifications = dict(Activity.objects.values_list("strava_activity_id", "workout_class"))
    saved_analysis = Activity.objects.get(strava_activity_id="fx-easy-1").analysis
    import_provider(SnapshotProvider(path))
    assert dict(Activity.objects.values_list("strava_activity_id", "workout_class")) == classifications
    assert Activity.objects.get(strava_activity_id="fx-easy-1").analysis == saved_analysis


class StreamlessProvider:
    def list_activities(self, start=None, end=None):
        return [{"id": "streamless", "name": "Easy", "start_local": "2026-08-24T08:00:00+08:00", "sport_type": "Run", "summary": {"distance": 5000, "moving_time": 1500, "elapsed_time": 1500}}]

    def get_activity_streams(self, activity_id):
        return {}


@pytest.mark.django_db
def test_streamless_reimport_removes_stale_stream():
    activity = Activity.objects.create(strava_activity_id="streamless", name="Old", start_time="2026-08-24T00:00:00Z", sport_type="Run", distance=5000, moving_time=1500, elapsed_time=1500)
    ActivityStream.objects.create(activity=activity, time=[0, 1], distance=[0, 1], heart_rate=[120, 121])
    import_provider(StreamlessProvider())
    assert not ActivityStream.objects.filter(activity__strava_activity_id="streamless").exists()
    refreshed = Activity.objects.get(strava_activity_id="streamless")
    assert refreshed.has_hr_stream is False
    assert "🌱 恢復與下一步" in refreshed.analysis


@pytest.mark.django_db
def test_reimport_strips_published_analysis_from_user_description():
    class PublishedDescriptionProvider(StreamlessProvider):
        def list_activities(self, start=None, end=None):
            payload = super().list_activities(start, end)[0]
            payload["description"] = merge_analysis_into_description("Athlete note", "恢復跑，明天輕鬆跑。")
            return [payload]

    import_provider(PublishedDescriptionProvider())

    activity = Activity.objects.get(strava_activity_id="streamless")
    assert activity.description == "Athlete note"
    assert activity.workout_class != "recovery"


@pytest.mark.django_db
def test_reimport_strips_generated_title_prefix_before_classification():
    class PrefixedTitleProvider(StreamlessProvider):
        def list_activities(self, start=None, end=None):
            payload = super().list_activities(start, end)[0]
            payload["name"] = "[Threshold] Morning Run"
            return [payload]

    import_provider(PrefixedTitleProvider())

    activity = Activity.objects.get(strava_activity_id="streamless")
    assert activity.name == "Morning Run"
    assert activity.workout_class != "threshold"


@pytest.mark.django_db
@pytest.mark.parametrize(("create_profile", "expected"), [(True, 165), (False, None)])
def test_import_passes_profile_tempo_hr_to_classifier(monkeypatch, create_profile, expected):
    from runtwin.athletes.models import AthleteProfile
    from runtwin.classification.rules import classify_activity

    if create_profile:
        AthleteProfile.objects.create(provisional_tempo_hr_low=165, provisional_tempo_hr_high=168)
    seen = []

    def spy(**kwargs):
        seen.append(kwargs["tempo_hr_low"])
        return classify_activity(**kwargs)

    monkeypatch.setattr("runtwin.ingestion.service.classify_activity", spy)

    import_provider(StreamlessProvider())

    assert seen == [expected]
    assert Activity.objects.get(strava_activity_id="streamless").classifier_version == "rules-v4"


@pytest.mark.django_db
def test_import_skips_payloads_without_id_or_start_and_fills_hr_from_stream():
    class MixedProvider:
        def list_activities(self, start=None, end=None):
            return [
                {"name": "No id", "start_local": "2026-08-24T08:00:00+08:00", "summary": {"distance": 5000, "moving_time": 1500}},
                {"id": "no-start", "name": "No start", "summary": {"distance": 5000, "moving_time": 1500}},
                {"id": "hr-from-stream", "name": "Run", "start_local": "2026-08-24T08:00:00+08:00", "sport_type": "Run",
                 "summary": {"distance": 1000, "moving_time": 300, "elapsed_time": 300}},
            ]

        def get_activity_streams(self, activity_id):
            return {"time": [0, 1, 2, 3], "heartrate": [120, 130, 140, 500], "distance": [0, 3, 6, 9]}

    result = import_provider(MixedProvider())

    assert result["created"] == 1
    activity = Activity.objects.get()
    assert activity.strava_activity_id == "hr-from-stream"
    assert activity.average_hr == 130
    assert activity.max_hr == 140


@pytest.mark.django_db
def test_analysis_failure_does_not_block_sync(monkeypatch):
    def fail_analysis(activity):
        raise RuntimeError("analysis unavailable")

    monkeypatch.setattr("runtwin.ingestion.service.build_activity_analysis", fail_analysis)

    result = import_provider(StreamlessProvider())

    assert result["created"] == 1
    assert Activity.objects.get(strava_activity_id="streamless").analysis == ""
    assert DataSyncRun.objects.latest("started_at").status == "complete"
