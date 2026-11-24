from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from runtwin.activities.models import Activity
from runtwin.ai.activity import (
    REQUIRED_HEADINGS,
    SYSTEM_PROMPT,
    ActivityAnalysisError,
    ActivityAnalyzer,
    build_activity_facts,
    build_training_history,
)
from runtwin.ai.client import AIGenerationError
from runtwin.athletes.models import AthleteProfile

FULL_ANALYSIS = "\n".join(f"{heading}\n內容" for heading in REQUIRED_HEADINGS)


class FakeGenerator:
    name = "fake"
    model = "fake-model"

    def __init__(self, text="", error=None):
        self.text = text
        self.error = error
        self.calls = []

    def generate_text(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.text


def activity():
    return Activity.objects.create(
        strava_activity_id="123",
        name="Tempo Run",
        description="felt controlled",
        start_time=timezone.now(),
        sport_type="Run",
        distance=10000,
        moving_time=2500,
        elapsed_time=2550,
        elevation_gain=50,
        average_hr=160,
        max_hr=175,
        average_pace=250,
        workout_class="tempo_threshold",
        classification_confidence=0.9,
        classification_reasons=["steady fast effort"],
        stream_features={"hr_drift_percent": 2.0},
        quality_issues=[],
        data_quality_score=100,
    )


@pytest.mark.django_db
def test_activity_analyzer_sends_facts_and_tags_source():
    generator = FakeGenerator(FULL_ANALYSIS)
    analyzer = ActivityAnalyzer(generator)

    result = analyzer.generate(activity())

    assert result == FULL_ANALYSIS
    assert analyzer.source == "ai:fake"
    call = generator.calls[0]
    assert call["system"] == SYSTEM_PROMPT
    assert call["max_output_tokens"] == 4096
    assert "felt controlled" in call["user"]


@pytest.mark.django_db
def test_activity_analyzer_rejects_missing_emoji_sections():
    with pytest.raises(ActivityAnalysisError, match="emoji 段落"):
        ActivityAnalyzer(FakeGenerator("只有普通文字")).generate(activity())


@pytest.mark.django_db
@pytest.mark.parametrize("missing", REQUIRED_HEADINGS)
def test_activity_analyzer_rejects_response_missing_any_new_heading(missing):
    text = "\n".join(f"{heading}\n內容" for heading in REQUIRED_HEADINGS if heading != missing)

    with pytest.raises(ActivityAnalysisError, match="emoji 段落"):
        ActivityAnalyzer(FakeGenerator(text)).generate(activity())


def test_system_prompt_lists_every_required_heading_and_rules():
    assert all(heading in SYSTEM_PROMPT for heading in REQUIRED_HEADINGS)
    assert "high_dew_point" in SYSTEM_PROMPT
    assert "不可要求或暗示更改分類" in SYSTEM_PROMPT


@pytest.mark.django_db
def test_activity_analyzer_wraps_provider_errors():
    generator = FakeGenerator(error=AIGenerationError("模型拒絕產生內容（refusal）。"))

    with pytest.raises(ActivityAnalysisError, match="refusal"):
        ActivityAnalyzer(generator).generate(activity())


@pytest.mark.django_db
def test_activity_analyzer_rejects_empty_response():
    with pytest.raises(ActivityAnalysisError, match="沒有回傳"):
        ActivityAnalyzer(FakeGenerator("")).generate(activity())


@pytest.mark.django_db
def test_activity_facts_include_goals_and_recent_context():
    AthleteProfile.objects.create(
        half_marathon_goal=timedelta(hours=1, minutes=45),
        marathon_goal=timedelta(hours=3, minutes=45),
        normal_weekly_distance=40,
    )
    current = activity()
    Activity.objects.create(
        strava_activity_id="122",
        name="Easy",
        start_time=current.start_time - timedelta(days=2),
        sport_type="Run",
        distance=5000,
        moving_time=1800,
        elapsed_time=1800,
        workout_class="easy",
    )

    facts = build_activity_facts(current)

    assert facts["runner_goals"]["half_marathon_goal_seconds"] == 6300
    assert facts["runner_goals"]["marathon_goal_seconds"] == 13500
    assert facts["training_history"]["run_count"] == 1
    assert facts["training_history"]["workout_class_counts"] == {"easy": 1}


@pytest.mark.django_db
def test_activity_facts_without_garmin_mark_it_unavailable_and_without_profile():
    facts = build_activity_facts(activity())

    assert facts["garmin_metrics"]["available"] is False
    assert "沒有 Garmin" in facts["garmin_metrics"]["note"]
    assert facts["runner_goals"] == {}
    assert facts["training_history"]["sufficient_for_trend"] is False


@pytest.mark.django_db
@pytest.mark.parametrize(("dew_point", "high"), [(21.5, True), (12.0, False)])
def test_activity_facts_include_garmin_metrics_and_dew_point_flag(dew_point, high):
    current = activity()
    current.garmin_metrics = {
        "version": "garmin-metrics-v1",
        "garmin_activity_id": "1000000001",
        "aerobic_training_effect": 3.8,
        "training_effect_label": "AEROBIC_BASE",
        "hr_zone_seconds": {"2": 3600.0},
        "weather": {"dew_point_c": dew_point},
    }
    current.save(update_fields=["garmin_metrics"])

    facts = build_activity_facts(current)

    garmin = facts["garmin_metrics"]
    assert garmin["available"] is True
    assert garmin["garmin_activity_id"] == "1000000001"
    assert garmin["aerobic_training_effect"] == 3.8
    assert garmin["hr_zone_seconds"] == {"2": 3600.0}
    assert garmin["high_dew_point"] is high


def _past_run(current, days_before, distance_km, workout_class="easy", **fields):
    return Activity.objects.create(
        strava_activity_id=f"h{days_before}",
        name="History",
        start_time=current.start_time - timedelta(days=days_before),
        sport_type="Run",
        distance=distance_km * 1000,
        moving_time=1800,
        elapsed_time=1800,
        workout_class=workout_class,
        **fields,
    )


@pytest.mark.django_db
def test_training_history_covers_twelve_weeks_with_trends():
    current = activity()
    for week in range(12):
        _past_run(current, week * 7 + 1, 8, stream_features={"pace_hr_efficiency_m_per_min_per_bpm": 1.0 + (11 - week) * 0.01})
    _past_run(current, 80, 21, workout_class="long", stream_features={"steady_run": True, "hr_drift_percent": 6.0})
    _past_run(current, 10, 20, workout_class="long", stream_features={"steady_run": True, "hr_drift_percent": 2.0})
    _past_run(current, 3, 6, stream_features={"pace_hr_efficiency_m_per_min_per_bpm": True, "steady_run": False})
    _past_run(current, 85, 30)  # outside the 12-week window
    Activity.objects.create(
        strava_activity_id="ride",
        name="Ride",
        start_time=current.start_time - timedelta(days=2),
        sport_type="Ride",
        distance=40000,
        moving_time=3600,
        elapsed_time=3600,
    )

    history = build_training_history(current)

    assert history["window_weeks"] == 12
    assert history["weeks_with_runs"] == 12
    assert history["sufficient_for_trend"] is True
    assert history["run_count"] == 15
    assert history["long_run_count"] == 2
    assert history["workout_class_counts"] == {"easy": 13, "long": 2}
    assert len(history["weekly"]) == 12
    assert history["weekly"][0]["weeks_before"] == 12
    assert history["weekly"][0]["long_run_count"] == 1
    assert history["weekly"][-1]["distance_km"] == 14.0
    assert history["easy_efficiency_trend"]["sample_count"] == 12
    assert history["easy_efficiency_trend"]["later_minus_earlier"] > 0
    assert history["steady_hr_drift_trend"] == {
        "sample_count": 2,
        "earlier_half_mean": 6.0,
        "later_half_mean": 2.0,
        "later_minus_earlier": -4.0,
    }
    assert [run["distance_km"] for run in history["latest_runs"][:2]] == [8.0, 6.0]
    assert len(history["latest_runs"]) == 8


@pytest.mark.django_db
def test_training_history_trend_is_empty_without_both_halves():
    current = activity()
    _past_run(current, 3, 10, stream_features={"pace_hr_efficiency_m_per_min_per_bpm": 1.1})

    trend = build_training_history(current)["easy_efficiency_trend"]

    assert trend == {"sample_count": 1, "earlier_half_mean": None, "later_half_mean": 1.1, "later_minus_earlier": None}
