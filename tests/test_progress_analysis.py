from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from runtwin.progress.analysis import _garmin_week, build_progress_analysis, build_training_context


def activity(week, *, distance_km, efficiency, workout_class="easy", drift=None, garmin=None, day=0):
    features = {"pace_hr_efficiency_m_per_min_per_bpm": efficiency, "steady_run": drift is not None, "hr_drift_percent": drift}
    return SimpleNamespace(
        start_time=datetime(2026, 1, 5, tzinfo=ZoneInfo("Asia/Taipei")) + timedelta(weeks=week, days=day),
        distance=distance_km * 1000,
        moving_time=3600,
        workout_class=workout_class,
        stream_features=features,
        garmin_metrics=garmin or {},
    )


def garmin(load, aerobic=3.0, z2=3000.0, z3=600.0, dew=15.0):
    return {
        "training_load": load,
        "aerobic_training_effect": aerobic,
        "hr_zone_seconds": {"1": 0.0, "2": z2, "3": z3, "4": 0, "5": True},
        "weather": {"dew_point_c": dew},
    }


def test_progress_analysis_includes_garmin_factor_when_correlated():
    items = []
    loads = [80, 240, 120, 260, 90, 250, 130, 270, 100, 280, 140, 290]
    for week, load in enumerate(loads):
        prior = loads[week - 1] if week else 80
        items.append(activity(week, distance_km=40, efficiency=1.0 + prior / 1000, garmin=garmin(load)))

    result = build_progress_analysis(items, today=datetime(2026, 4, 6).date())

    assert result["garmin_week_count"] == 12
    factor = next(item for item in result["factors"] if item["key"] == "garmin_training_load")
    assert factor["source"] == "garmin"
    assert factor["label"] == "Garmin 週訓練負荷"
    assert factor["correlation"] > 0.9
    assert all(item["source"] == "strava" for item in result["factors"] if not item["key"].startswith("garmin_"))
    assert "Garmin 因素" in result["limitations"][-1]


def test_progress_analysis_skips_garmin_factors_without_garmin_data():
    items = [activity(week, distance_km=20 + week * 5, efficiency=1.0 + week * 0.02) for week in range(12)]

    result = build_progress_analysis(items, today=datetime(2026, 4, 6).date())

    assert result["garmin_week_count"] == 0
    assert not any(item["source"] == "garmin" for item in result["factors"])
    assert result["training_context"]["garmin"]["matched_run_count"] == 0


def test_progress_analysis_caps_factors_per_source(monkeypatch):
    from runtwin.progress import analysis

    extra = tuple(analysis.FactorDefinition("distance_km", f"S{index}", "km", "higher") for index in range(8))
    garmin_extra = tuple(analysis.FactorDefinition("garmin_training_load", f"G{index}", "load", "higher", "garmin") for index in range(6))
    monkeypatch.setattr(analysis, "FACTORS", extra + garmin_extra)
    items = []
    loads = [80, 240, 120, 260, 90, 250, 130, 270, 100, 280, 140, 290]
    for week, load in enumerate(loads):
        prior = loads[week - 1] if week else 80
        items.append(activity(week, distance_km=load / 5, efficiency=1.0 + prior / 1000, garmin=garmin(load)))

    factors = build_progress_analysis(items, today=datetime(2026, 4, 6).date())["factors"]

    assert [item["source"] for item in factors] == ["strava"] * 6 + ["garmin"] * 4


def test_progress_analysis_skips_factor_without_rank_variance(monkeypatch):
    monkeypatch.setattr("runtwin.progress.analysis._spearman", lambda first, second: None)
    items = [activity(week, distance_km=20 + week * 5, efficiency=1.0 + week * 0.02) for week in range(12)]

    result = build_progress_analysis(items, today=datetime(2026, 4, 6).date())

    assert result["status"] == "limited"
    assert result["factors"] == []


def test_progress_analysis_without_runs_has_empty_context():
    result = build_progress_analysis([], today=datetime(2026, 4, 6).date())

    assert result["complete_week_count"] == 0
    assert result["garmin_week_count"] == 0
    assert result["training_context"]["window_weeks"] == 0


@pytest.mark.django_db
def test_progress_analysis_reads_runs_from_database():
    from runtwin.activities.models import Activity

    Activity.objects.create(
        strava_activity_id="1",
        name="Run",
        start_time=datetime(2026, 3, 2, 7, tzinfo=ZoneInfo("Asia/Taipei")),
        sport_type="Run",
        distance=10000,
        moving_time=3600,
        elapsed_time=3600,
        garmin_metrics=garmin(150),
    )

    result = build_progress_analysis(today=datetime(2026, 3, 16).date())

    assert result["garmin_week_count"] == 1
    assert result["training_context"]["garmin"]["average_weekly_training_load"] == 150.0


def test_garmin_week_aggregates_and_ignores_bad_values():
    items = [
        activity(0, distance_km=10, efficiency=1.0, garmin=garmin(100, aerobic=3.0, z2=3000, z3=1000, dew=20.0)),
        activity(0, distance_km=10, efficiency=1.0, garmin=garmin(50, aerobic=4.0, z2=1000, z3=1000, dew=12.0)),
        activity(0, distance_km=10, efficiency=1.0, garmin={"training_load": "x", "aerobic_training_effect": True, "hr_zone_seconds": "bad", "weather": "humid"}),
        activity(0, distance_km=10, efficiency=1.0),
    ]

    week = _garmin_week(items)

    assert week["garmin_run_count"] == 3
    assert week["garmin_training_load"] == 150
    assert week["garmin_aerobic_te"] == 3.5
    assert week["garmin_z2_share"] == pytest.approx(4000 / 6000 * 100)
    assert week["garmin_high_dew_point_runs"] == 1


def test_garmin_week_returns_none_without_matches():
    week = _garmin_week([activity(0, distance_km=10, efficiency=1.0)])

    assert week == {
        "garmin_run_count": 0,
        "garmin_training_load": None,
        "garmin_aerobic_te": None,
        "garmin_z2_share": None,
        "garmin_high_dew_point_runs": None,
    }


def test_training_context_reports_five_points_and_garmin():
    items = []
    for week in range(12):
        items.append(activity(week, distance_km=40, efficiency=1.0 + week * 0.01, garmin=garmin(200, dew=19.0 if week >= 10 else 15.0)))
        items.append(activity(week, distance_km=20, efficiency=None, workout_class="long", drift=6.0 if week < 6 else 3.0, day=5))

    context = build_progress_analysis(items, today=datetime(2026, 3, 30).date())["training_context"]

    assert context["window_weeks"] == 12
    assert context["weeks_with_runs"] == 12
    assert context["sufficient_for_trend"] is True
    assert context["run_count"] == 24
    assert context["average_weekly_distance_km"] == 60.0
    assert context["recent_4_week_distance_km"] == 60.0
    assert context["long_run_count"] == 12
    assert context["workout_class_counts"] == {"easy": 12, "long": 12}
    assert context["easy_efficiency_trend"]["later_minus_earlier"] == pytest.approx(0.06)
    assert context["steady_hr_drift_trend"] == {"sample_count": 12, "earlier_half_mean": 6.0, "later_half_mean": 3.0, "later_minus_earlier": -3.0}
    assert context["garmin"] == {
        "weeks_with_data": 12,
        "matched_run_count": 12,
        "average_weekly_training_load": 200.0,
        "average_aerobic_training_effect": 3.0,
        "z1_z2_share_percent": pytest.approx(83.3),
        "high_dew_point_runs": 2,
    }
    assert context["weekly"][0]["garmin_training_load"] == 200.0


def test_training_context_handles_no_weeks_and_sparse_weeks():
    empty = build_training_context([])
    assert empty["window_weeks"] == 0
    assert empty["average_weekly_distance_km"] is None
    assert empty["recent_4_week_distance_km"] is None
    assert empty["sufficient_for_trend"] is False

    items = [activity(0, distance_km=10, efficiency=1.2), activity(8, distance_km=10, efficiency=1.3)]
    context = build_progress_analysis(items, today=datetime(2026, 3, 9).date())["training_context"]
    assert context["weeks_with_runs"] == 2
    assert context["sufficient_for_trend"] is False
    assert context["steady_hr_drift_trend"]["later_minus_earlier"] is None
    assert context["garmin"]["average_weekly_training_load"] is None
    assert context["weekly"][1]["garmin_training_load"] is None


def test_progress_analysis_requires_enough_complete_weeks():
    items = [activity(week, distance_km=30 + week, efficiency=1.3 + week * 0.01) for week in range(5)]

    result = build_progress_analysis(items, today=datetime(2026, 2, 16).date())

    assert result["status"] == "insufficient_data"
    assert result["factors"] == []


def test_progress_analysis_finds_lagged_weekly_distance_association():
    items = []
    distances = [20, 60, 30, 70, 25, 65, 35, 75, 40, 80, 45, 85]
    for week, distance in enumerate(distances):
        prior_distance = distances[week - 1] if week else 20
        items.append(activity(week, distance_km=distance, efficiency=1.0 + prior_distance / 200))

    result = build_progress_analysis(items, today=datetime(2026, 4, 6).date())

    assert result["status"] == "ok"
    distance = next(item for item in result["factors"] if item["key"] == "distance_km")
    assert distance["correlation"] > 0.9
    assert distance["direction_text"] == "較高時，下一週效率通常較好"
    assert result["outcome_label"].startswith("Easy／Long")
    assert "不代表因果" in result["limitations"][0]


def test_progress_analysis_excludes_current_incomplete_week():
    items = [activity(week, distance_km=40, efficiency=1.4) for week in range(9)]
    current = activity(10, distance_km=100, efficiency=2.0)
    items.append(current)

    result = build_progress_analysis(items, today=datetime(2026, 3, 16).date())

    assert all(point["week_start"] != "2026-03-16" for point in result["trend"])
