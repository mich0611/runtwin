import pytest

from runtwin.classification.rules import CLASSIFIER_VERSION, _easy_hr_ceiling, classify_activity


def base_features(**overrides):
    result = {"status": "ok", "median_pace_seconds_per_km": 290, "speed_variability": 0.1, "progression_ratio": 1.0, "has_repeated_fast_recovery": False, "fast_block_count": 0}
    result.update(overrides)
    return result


def test_name_alone_does_not_make_tempo():
    result = classify_activity(name="Tempo", description="", distance_m=3000, moving_time_s=600, features={"status": "insufficient_data"})
    assert result["workout_class"] != "tempo_threshold"


def test_interval_requires_stream_pattern():
    result = classify_activity(name="6 x 800m", description="間歇", distance_m=10000, moving_time_s=3200, features=base_features(has_repeated_fast_recovery=True, fast_block_count=6))
    assert result["workout_class"] == "interval"
    assert result["confidence"] == 0.9

    unnamed = classify_activity(name="Evening Run", description="", distance_m=10000, moving_time_s=3200, features=base_features(has_repeated_fast_recovery=True, fast_block_count=6))
    assert unnamed["workout_class"] == "interval"
    assert unnamed["confidence"] == 0.82
    assert "名稱提供間歇語意作為輔助證據" not in unnamed["reasons"]


def test_progression_detected_from_stream():
    result = classify_activity(name="Evening Run", description="", distance_m=12000, moving_time_s=3600, features=base_features(progression_ratio=1.14))
    assert result["workout_class"] == "progression"
    assert result["confidence"] == 0.78

    named = classify_activity(name="Progression Run", description="", distance_m=12000, moving_time_s=3600, features=base_features(progression_ratio=1.14))
    assert named["confidence"] == 0.86
    assert "名稱與 stream 特徵一致" in named["reasons"]


def test_long_run_confidence_depends_on_name():
    plain = classify_activity(name="Sunday Run", description="", distance_m=20000, moving_time_s=6000, features=base_features())
    named = classify_activity(name="Long Run", description="", distance_m=20000, moving_time_s=6000, features=base_features())

    assert plain["workout_class"] == named["workout_class"] == "long"
    assert plain["confidence"] == 0.72
    assert named["confidence"] == 0.82
    assert "名稱與距離特徵一致" in named["reasons"]


def test_tempo_and_threshold_are_distinct_when_name_and_stream_agree():
    tempo = classify_activity(name="Tempo Run", description="", distance_m=10000, moving_time_s=2700, features=base_features(median_pace_seconds_per_km=250))
    threshold = classify_activity(name="Threshold Run", description="", distance_m=10000, moving_time_s=2500, features=base_features(median_pace_seconds_per_km=235))

    assert tempo["workout_class"] == "tempo"
    assert threshold["workout_class"] == "threshold"


def test_user_authored_bracket_prefix_remains_classification_evidence():
    result = classify_activity(
        name="[Taipei Marathon] PB day",
        description="",
        distance_m=42195,
        moving_time_s=10800,
        features=base_features(),
    )

    assert result["workout_class"] == "race"


def test_fartlek_requires_variable_stream_pattern():
    result = classify_activity(
        name="Fartlek Run",
        description="",
        distance_m=9000,
        moving_time_s=3000,
        features=base_features(has_repeated_fast_recovery=True, fast_block_count=5),
    )

    assert result["workout_class"] == "fartlek"


def test_strava_personal_best_is_classified_as_race_effort():
    result = classify_activity(
        name="Evening Run",
        description="一路從 22 分台帶我到 18 分台",
        distance_m=5000.1,
        moving_time_s=1125,
        features=base_features(median_pace_seconds_per_km=222.22),
        summary={"best_efforts": [{"name": "5K", "distance": 5000, "pr_rank": 1}]},
    )

    assert result["workout_class"] == "race"
    assert result["confidence"] == 0.95
    assert "5K" in result["reasons"][0]


def test_segment_pr_alone_does_not_make_activity_a_race_effort():
    result = classify_activity(
        name="Evening Run",
        description="",
        distance_m=5000,
        moving_time_s=1800,
        features=base_features(median_pace_seconds_per_km=300),
        summary={
            "segment_efforts": [{"name": "Local segment", "pr_rank": 1}],
            "best_efforts": [{"name": "5K", "distance": 5000, "pr_rank": None}],
        },
    )

    assert result["workout_class"] == "easy"


def gray_zone_run(tempo_hr_low=165, **feature_overrides):
    """Gray-zone run: 8.02 km at 4:42/km, median HR 140, steady."""
    features = base_features(median_pace_seconds_per_km=282.49, speed_variability=0.1283, steady_run=True, median_hr_bpm=140.0)
    features.update(feature_overrides)
    return classify_activity(
        name="Evening Run",
        description="",
        distance_m=8020,
        moving_time_s=2273,
        features=features,
        tempo_hr_low=tempo_hr_low,
    )


def test_gray_zone_pace_with_low_heart_rate_is_easy():
    result = gray_zone_run()

    assert result["workout_class"] == "easy"
    assert result["confidence"] == 0.6
    assert result["classifier_version"] == CLASSIFIER_VERSION == "rules-v4"
    assert "改以心率判斷" in result["reasons"][0]
    assert "140 bpm ≤ 節奏心率下限的 90%（148 bpm）" in result["reasons"][1]


@pytest.mark.parametrize(
    ("tempo_hr_low", "overrides"),
    [
        (165, {"median_hr_bpm": 149.0}),
        (165, {"steady_run": False}),
        (165, {"has_repeated_fast_recovery": True}),
        (165, {"median_pace_seconds_per_km": 284.9, "median_hr_bpm": 155.0}),
        (165, {"median_pace_seconds_per_km": 270.5, "speed_variability": 0.3, "median_hr_bpm": 160.0}),
        (165, {"median_hr_bpm": None}),
        (165, {"median_hr_bpm": True}),
        (165, {"status": "insufficient_data"}),
        (None, {}),
        (0, {}),
        ("165", {}),
    ],
)
def test_gray_zone_stays_unknown_without_clear_easy_heart_rate(tempo_hr_low, overrides):
    result = gray_zone_run(tempo_hr_low, **overrides)

    assert result["workout_class"] == "unknown"
    assert result["confidence"] == 0.3


def test_gray_zone_heart_rate_exactly_at_ceiling_is_easy():
    assert gray_zone_run(median_hr_bpm=148.5)["workout_class"] == "easy"


def test_heart_rate_rule_does_not_change_existing_pace_bands():
    slow = gray_zone_run(median_pace_seconds_per_km=285, median_hr_bpm=170.0)
    fast = gray_zone_run(median_pace_seconds_per_km=265, median_hr_bpm=120.0)

    boundary = gray_zone_run(median_pace_seconds_per_km=270, median_hr_bpm=120.0)
    assert slow["workout_class"] == "easy"
    assert slow["confidence"] == 0.62
    assert fast["workout_class"] == "tempo_threshold"
    assert boundary["workout_class"] == "tempo_threshold"


def test_gray_zone_lower_edge_with_low_heart_rate_is_easy():
    result = gray_zone_run(median_pace_seconds_per_km=270.5, speed_variability=0.3, median_hr_bpm=135.0)

    assert result["workout_class"] == "easy"
    assert result["confidence"] == 0.6


@pytest.mark.parametrize(("value", "expected"), [(165, 148.5), (160.0, 144.0), (None, None), (0, None), (-5, None), (True, None), ("165", None)])
def test_easy_hr_ceiling(value, expected):
    assert _easy_hr_ceiling(value) == expected


def test_short_best_effort_inside_easy_run_does_not_make_activity_a_race_effort():
    result = classify_activity(
        name="Morning Run",
        description="",
        distance_m=10000,
        moving_time_s=3000,
        features=base_features(median_pace_seconds_per_km=300),
        summary={"best_efforts": [{"name": "400m", "distance": 400, "pr_rank": 1}]},
    )

    assert result["workout_class"] == "easy"
