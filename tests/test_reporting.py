from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from runtwin.activities.models import Activity
from runtwin.ai.fallback import DeterministicFallbackProvider
from runtwin.reporting.facts import build_weekly_facts
from runtwin.reporting.models import InsightEvidence, WeeklyReport
from runtwin.reporting.schemas import AIReportSchema, WeeklyFactsSchema
from runtwin.reporting.service import generate_facts, save_validated_report


def create_run(activity_id, when, distance=10000, workout_class="easy", average_hr=140, has_hr=True):
    return Activity.objects.create(
        strava_activity_id=activity_id,
        name=f"Run {activity_id}",
        start_time=when,
        sport_type="Run",
        distance=distance,
        moving_time=int(distance / 3.2),
        elapsed_time=int(distance / 3.2),
        elevation_gain=30,
        average_hr=average_hr if has_hr else None,
        max_hr=155 if has_hr else None,
        average_pace=312.5,
        workout_class=workout_class,
        classification_confidence=.8,
        has_hr_stream=has_hr,
        has_pace_stream=True,
        stream_features={},
        data_quality_score=95,
    )


@pytest.mark.django_db
def test_four_week_average(athlete):
    zone = ZoneInfo("Asia/Taipei")
    current = datetime(2026, 8, 24, 8, tzinfo=zone)
    create_run("current", current, 20000)
    for index, km in enumerate([10000, 20000, 30000, 40000], start=1):
        create_run(f"prior-{index}", current - timedelta(days=7 * index), km)
    facts = build_weekly_facts(athlete, current.date())
    assert facts["comparisons"]["distance_vs_four_week_average"]["value"] == -20.0
    assert facts["comparisons"]["distance_vs_four_week_average"]["sample_size"] == 4


@pytest.mark.django_db
def test_weekly_facts_schema_and_empty_week(athlete):
    facts = build_weekly_facts(athlete, datetime(2026, 8, 24).date())
    validated = WeeklyFactsSchema.model_validate(facts)
    assert validated.metrics["run_count"].value == 0
    assert validated.metrics["average_hr"].status == "insufficient_data"


@pytest.mark.django_db
def test_ai_schema_and_unknown_activity_rejected(athlete):
    activity = create_run("real-id", datetime(2026, 8, 24, 8, tzinfo=ZoneInfo("Asia/Taipei")))
    report = generate_facts(athlete, datetime(2026, 8, 24).date())
    payload = DeterministicFallbackProvider().generate(report.facts_json)
    payload["positives"][0]["related_activity_ids"] = ["invented-id"]
    with pytest.raises(ValueError, match="不存在"):
        save_validated_report(report, payload, "test")


@pytest.mark.django_db
def test_weekly_report_rerun_is_idempotent(athlete):
    create_run("run-1", datetime(2026, 8, 24, 8, tzinfo=ZoneInfo("Asia/Taipei")))
    first = generate_facts(athlete, datetime(2026, 8, 24).date())
    save_validated_report(first, DeterministicFallbackProvider().generate(first.facts_json), "fallback")
    second = generate_facts(athlete, datetime(2026, 8, 24).date())
    save_validated_report(second, DeterministicFallbackProvider().generate(second.facts_json), "fallback")
    assert WeeklyReport.objects.count() == 1
    assert first.pk == second.pk
    assert InsightEvidence.objects.filter(weekly_report=second).count() > 0


@pytest.mark.django_db
def test_ai_evidence_value_must_match_facts(athlete):
    create_run("real-id", datetime(2026, 8, 24, 8, tzinfo=ZoneInfo("Asia/Taipei")))
    report = generate_facts(athlete, datetime(2026, 8, 24).date())
    payload = DeterministicFallbackProvider().generate(report.facts_json)
    payload["positives"][0]["evidence"][0]["metric_value"] = 999
    with pytest.raises(ValueError, match="證據值不符"):
        save_validated_report(report, payload, "test")


def test_ai_response_schema_rejects_extra_fields():
    with pytest.raises(ValidationError):
        AIReportSchema.model_validate({"unexpected": True})


def test_efficiency_unit_scaling():
    from runtwin.features.activity import calculate_stream_features

    streams = {
        "time": list(range(0, 2401, 60)),
        "distance": [index * 200 for index in range(41)],
        "velocity_smooth": [3.333] * 41,
        "heart_rate": [150] * 41,
        "moving": [True] * 41,
    }
    result = calculate_stream_features(streams, 2400, 8000)
    assert result["pace_hr_efficiency_m_per_min_per_bpm"] == pytest.approx(1.3332, abs=0.001)
