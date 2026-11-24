from runtwin.features.activity import calculate_stream_features


def test_hr_drift_for_stable_run():
    seconds = list(range(0, 2401, 60))
    streams = {
        "time": seconds,
        "distance": [index * 200 for index in range(len(seconds))],
        "velocity_smooth": [3.333] * len(seconds),
        "heart_rate": [140] * (len(seconds) // 2) + [147] * (len(seconds) - len(seconds) // 2),
        "moving": [True] * len(seconds),
    }
    result = calculate_stream_features(streams, 2400, 8000)
    assert result["steady_run"] is True
    assert 4 < result["hr_drift_percent"] < 6


def _minute_streams(speeds, hr=140):
    seconds = [index * 60 for index in range(len(speeds))]
    distance, total = [], 0.0
    for speed in speeds:
        distance.append(total)
        total += speed * 60
    return {
        "time": seconds,
        "distance": distance,
        "velocity_smooth": speeds,
        "heart_rate": [hr] * len(speeds),
        "moving": [True] * len(speeds),
    }


def test_short_slowdowns_do_not_disqualify_steady_run():
    # Regression: two traffic-light minutes made max-min range exceed 12% and dropped HR drift.
    speeds = [3.35] * 40
    speeds[10] = 2.7
    speeds[25] = 2.8

    result = calculate_stream_features(_minute_streams(speeds), 2400, 8000)

    assert result["steady_run"] is True
    assert result["hr_drift_percent"] is not None


def test_progression_run_is_not_steady():
    speeds = [3.0 + index * 0.02 for index in range(40)]

    result = calculate_stream_features(_minute_streams(speeds), 2400, 8000)

    assert result["steady_run"] is False
    assert result["hr_drift_percent"] is None
