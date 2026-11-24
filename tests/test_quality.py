import pytest

from runtwin.quality.checks import assess_stream_quality


def test_missing_hr_is_reported():
    result = assess_stream_quality({"time": [0, 1], "distance": [0, 3], "velocity_smooth": [3, 3]}, 2, 2)
    assert not result["has_hr_stream"]
    assert "missing_hr" in {item["code"] for item in result["issues"]}


def test_invalid_hr_is_excluded():
    result = assess_stream_quality({"time": [0, 1, 2], "distance": [0, 3, 6], "heart_rate": [20, 150, 260], "velocity_smooth": [3, 3, 3]}, 3, 3)
    assert result["has_hr_stream"]
    assert result["hr_coverage"] == pytest.approx(1 / 3, abs=0.0001)
    assert "invalid_hr" in {item["code"] for item in result["issues"]}


def test_long_stop_is_reported():
    result = assess_stream_quality({"time": [0, 1000], "distance": [0, 3000], "heart_rate": [120, 140], "velocity_smooth": [3, 3]}, 600, 1000)
    assert result["long_stop_ratio"] == 0.4
    assert "long_stops" in {item["code"] for item in result["issues"]}
