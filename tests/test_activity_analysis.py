from types import SimpleNamespace

import pytest

from runtwin.features.activity_analysis import (
    _next_steps,
    _overall_rating,
    _stimulus_summary,
    build_activity_analysis,
    high_dew_point,
)

HEADINGS = ("🏃 活動判讀", "⭐ 整體評比", "📊 數據觀察", "🎯 這堂課練了什麼", "🌱 恢復與下一步", "🧭 下一步")


def run(**overrides):
    fields = {
        "distance": 10000,
        "moving_time": 3000,
        "average_pace": 300,
        "average_hr": 150,
        "max_hr": 165,
        "workout_class": "easy",
        "get_workout_class_display": lambda: "輕鬆跑",
        "stream_features": {},
        "raw_summary": {},
        "quality_issues": [],
        "garmin_metrics": {},
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def history(weekly_distances, long_run_count=1, sufficient=True):
    return {
        "sufficient_for_trend": sufficient,
        "long_run_count": long_run_count,
        "weekly": [{"distance_km": value} for value in weekly_distances],
    }


def test_build_activity_analysis_describes_progression_and_recovery():
    activity = SimpleNamespace(
        distance=20000,
        moving_time=5700,
        average_pace=285,
        average_hr=147.2,
        max_hr=172,
        workout_class="progression",
        get_workout_class_display=lambda: "漸速跑",
        stream_features={
            "median_cadence_spm": 180.2,
            "progression_ratio": 1.08,
            "hr_drift_percent": 3.2,
        },
        raw_summary={"average_watts": 325},
        quality_issues=[],
        garmin_metrics={},
    )

    result = build_activity_analysis(activity)

    assert result.startswith("🏃 活動判讀")
    assert all(heading in result for heading in HEADINGS)
    assert "完成 20.00 km" in result
    assert "平均配速 4:45/km" in result
    assert "有明顯漸速" in result
    assert "48 小時" in result


def test_build_activity_analysis_handles_missing_stream_data():
    activity = SimpleNamespace(
        distance=5000,
        moving_time=1800,
        average_pace=360,
        average_hr=None,
        max_hr=None,
        workout_class="unknown",
        get_workout_class_display=lambda: "未知",
        stream_features={"status": "insufficient_data"},
        raw_summary={},
        quality_issues=[{"code": "missing_hr"}],
        garmin_metrics=None,
    )

    result = build_activity_analysis(activity)

    assert all(heading in result for heading in HEADINGS)
    assert "平均配速 6:00/km" in result
    assert "分類證據有限" in result
    assert "資料提醒" in result
    assert "沒有 Garmin 訓練效果資料" in result
    assert "訓練紀錄不足以看出趨勢" in result


def test_build_activity_analysis_uses_garmin_weather_and_history():
    activity = run(
        stream_features={"steady_run": True, "hr_drift_percent": 2.0},
        garmin_metrics={
            "aerobic_training_effect": 3.2,
            "anaerobic_training_effect": 0.4,
            "training_effect_label": "AEROBIC_BASE",
            "hr_zone_seconds": {"1": 120.0, "2": 2400.0, "3": 480.0},
            "weather": {"dew_point_c": 21.5},
        },
    )

    result = build_activity_analysis(activity, history([30] * 8 + [45] * 4))

    assert "Garmin 訓練效果有氧 3.2、無氧 0.4，主要刺激偏有氧基礎" in result
    assert "心率以 Z2 為主（約 80%）" in result
    assert "露點 21.5°C 偏高" in result
    assert "不代表體能下降" in result
    assert "完成品質良好" in result
    assert "高於前段的 30.0 km" in result


@pytest.mark.parametrize(
    ("overrides", "present", "absent"),
    [
        ({"workout_class": "interval", "stream_features": {"has_repeated_fast_recovery": True}}, "符合間歇型態", "有明顯漸速"),
        ({"stream_features": {"progression_ratio": 0.9}}, "可留意疲勞或路況影響", "有明顯漸速"),
        ({"stream_features": {"progression_ratio": 1.0, "hr_drift_percent": 7.5}}, "可能受疲勞、補水或環境影響", "後半速度"),
        ({"stream_features": {"hr_drift_percent": -7.5}}, "可用 stream 證據不足", "穩定跑心率漂移"),
        ({"stream_features": {"progression_ratio": "fast", "hr_drift_percent": "n/a"}}, "可用 stream 證據不足", "後半速度"),
        ({"workout_class": "race", "average_hr": None}, "48–72 小時以休息", "平均心率"),
        ({"workout_class": "long"}, "長距離後隔天", "平均心率 0"),
        ({"workout_class": "recovery"}, "維持低強度即可", "平均心率 0"),
        ({"garmin_metrics": {"weather": {"dew_point_c": 12.0}}}, "🧭 下一步", "露點"),
    ],
)
def test_build_activity_analysis_observation_and_recovery_paths(overrides, present, absent):
    result = build_activity_analysis(run(**overrides))

    assert all(heading in result for heading in HEADINGS)
    assert present in result
    assert absent not in result


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        ({"weather": {"dew_point_c": 18.0}}, 18.0),
        ({"weather": {"dew_point_c": 17.9}}, None),
        ({"weather": {"dew_point_c": True}}, None),
        ({"weather": {"dew_point_c": "20"}}, None),
        ({"weather": "humid"}, None),
        ({}, None),
        (None, None),
    ],
)
def test_high_dew_point_threshold_and_bad_values(metrics, expected):
    assert high_dew_point(metrics) == expected


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"quality_issues": [{"code": "gps"}], "data_quality_score": 69}, "資料品質不足"),
        ({"quality_issues": [{"code": "gps"}]}, "資料品質不足"),
        (
            {
                "quality_issues": [{"code": "gps_spikes"}],
                "data_quality_score": 90,
                "stream_features": {"steady_run": True, "hr_drift_percent": 1.86},
                "workout_class": "long",
                "get_workout_class_display": lambda: "長跑",
            },
            "以長跑來看，配速穩定且心率漂移小，完成品質良好",
        ),
        ({"quality_issues": [{"code": "gps"}], "data_quality_score": 70, "workout_class": "unknown"}, "分類證據有限"),
        ({"workout_class": "unknown"}, "分類證據有限"),
        ({"stream_features": {"steady_run": True, "hr_drift_percent": -4.0}}, "完成品質良好"),
        ({"stream_features": {"steady_run": True, "hr_drift_percent": 7.5}}, "品質評估保守"),
        ({"stream_features": {"steady_run": True, "hr_drift_percent": None}}, "品質評估保守"),
        ({"stream_features": {"steady_run": False, "hr_drift_percent": 1.0}}, "品質評估保守"),
    ],
)
def test_overall_rating_paths(overrides, expected):
    activity = run(**overrides)

    assert expected in _overall_rating(activity, activity.stream_features)


@pytest.mark.parametrize(
    ("workout_class", "garmin", "expected"),
    [
        ("easy", {"aerobic_training_effect": 4.2, "anaerobic_training_effect": 1.0, "training_effect_label": "lactate_threshold"}, "偏閾值"),
        ("easy", {"aerobic_training_effect": 3.0, "anaerobic_training_effect": 3.5, "training_effect_label": "UNKNOWN_LABEL"}, "偏無氧"),
        ("easy", {"aerobic_training_effect": 4.1, "anaerobic_training_effect": 1.0, "training_effect_label": None}, "偏閾值"),
        ("easy", {"aerobic_training_effect": 2.8, "anaerobic_training_effect": 0.2}, "偏有氧基礎"),
        ("interval", {"aerobic_training_effect": 3.0, "anaerobic_training_effect": None}, "依分類推估主要刺激偏無氧"),
        ("unknown", {}, "暫不判斷刺激類型"),
        ("race", {}, "暫不判斷刺激類型"),
    ],
)
def test_stimulus_summary_paths(workout_class, garmin, expected):
    assert expected in _stimulus_summary(workout_class, garmin)


@pytest.mark.parametrize(
    ("zones", "expected_zone"),
    [
        ({"4": 900.0, "5": 300.0, "1": 0, "2": True, "3": "x"}, "Z4 為主（約 75%）"),
        ({"1": 0}, None),
        ("not-a-dict", None),
    ],
)
def test_stimulus_summary_hr_zones(zones, expected_zone):
    result = _stimulus_summary("easy", {"hr_zone_seconds": zones})

    if expected_zone:
        assert expected_zone in result
    else:
        assert "心率以" not in result


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "不足以看出趨勢"),
        ({}, "不足以看出趨勢"),
        (history([40] * 12, sufficient=False), "不足以看出趨勢"),
        (history([30] * 8 + [45] * 4), "先持平，不再加量"),
        (history([50] * 8 + [30] * 4), "每週增幅不超過 10%"),
        (history([40] * 12), "可維持目前的訓練結構"),
        (history([40] * 4), "不足以看出趨勢"),
        ({"sufficient_for_trend": True, "long_run_count": 1}, "不足以看出趨勢"),
        (history([40] * 5), "可維持目前的訓練結構"),
    ],
)
def test_next_steps_paths(value, expected):
    assert expected in _next_steps(value)


def test_next_steps_suggests_long_run_only_when_missing():
    assert "沒有長跑" in _next_steps(history([40] * 12, long_run_count=0))
    assert "沒有長跑" not in _next_steps(history([40] * 12, long_run_count=2))
