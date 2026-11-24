from datetime import datetime, timezone

from runtwin.providers.garmin_match import match_garmin_activity, parse_garmin_start_gmt

START = datetime(2026, 11, 8, 12, 32, 57, tzinfo=timezone.utc)


def garmin(activity_id, start, distance=20008.76):
    return {"activityId": activity_id, "startTimeGMT": start, "distance": distance}


def test_parse_naive_gmt_string_as_utc():
    assert parse_garmin_start_gmt("2026-11-08 12:32:57") == START


def test_parse_converts_explicit_offset_to_utc():
    assert parse_garmin_start_gmt("2026-11-08T20:32:57+08:00") == START


def test_parse_rejects_missing_blank_and_invalid_values():
    assert parse_garmin_start_gmt(None) is None
    assert parse_garmin_start_gmt("   ") is None
    assert parse_garmin_start_gmt("not-a-date") is None


def test_match_returns_activity_within_tolerances():
    found = match_garmin_activity(START, 20008.0, [garmin(1, "2026-11-08 12:33:30")])
    assert found["activityId"] == 1


def test_match_rejects_start_time_beyond_two_minutes():
    assert match_garmin_activity(START, 20008.0, [garmin(1, "2026-11-08 12:35:30")]) is None


def test_match_rejects_distance_beyond_five_percent():
    assert match_garmin_activity(START, 20008.0, [garmin(1, "2026-11-08 12:32:57", 18000.0)]) is None


def test_match_prefers_closest_start_time():
    candidates = [garmin(1, "2026-11-08 12:34:20"), garmin(2, "2026-11-08 12:33:05"), garmin(3, "2026-11-08 12:33:50")]
    assert match_garmin_activity(START, 20008.0, candidates)["activityId"] == 2


def test_match_skips_candidates_without_valid_start():
    candidates = [{"activityId": 1, "distance": 20008.0}, garmin(2, "2026-11-08 12:33:00")]
    assert match_garmin_activity(START, 20008.0, candidates)["activityId"] == 2


def test_match_ignores_distance_when_unavailable():
    no_garmin_distance = {"activityId": 1, "startTimeGMT": "2026-11-08 12:33:00", "distance": None}
    assert match_garmin_activity(START, 20008.0, [no_garmin_distance])["activityId"] == 1
    assert match_garmin_activity(START, 0, [garmin(2, "2026-11-08 12:33:00", 5000.0)])["activityId"] == 2