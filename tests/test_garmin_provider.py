from datetime import datetime, timezone

import pytest

from runtwin.providers.garmin import (
    GarminMetricsProvider,
    GarminUnavailableError,
    extract_activity_metrics,
    extract_weather,
)


def test_extract_activity_metrics_keeps_numbers_labels_and_zones():
    item = {
        "aerobicTrainingEffect": 3.8,
        "trainingEffectLabel": "AEROBIC_BASE",
        "activityTrainingLoad": 156.0294,
        "hrTimeInZone_3": 5276.361,
        "averageHR": 140,
    }

    metrics = extract_activity_metrics(item)

    assert metrics == {
        "aerobic_training_effect": 3.8,
        "training_effect_label": "AEROBIC_BASE",
        "training_load": 156.03,
        "hr_zone_seconds": {"3": 5276.36},
    }


def test_extract_activity_metrics_drops_missing_empty_and_boolean_values():
    item = {"aerobicTrainingEffect": None, "trainingEffectLabel": "", "normPower": True}

    assert extract_activity_metrics(item) == {}


def test_extract_weather_converts_fahrenheit_to_celsius():
    weather = {"temp": 76, "apparentTemp": 76, "dewPoint": 65, "relativeHumidity": 71}

    assert extract_weather(weather) == {
        "temperature_c": 24.4,
        "apparent_temperature_c": 24.4,
        "dew_point_c": 18.3,
        "humidity_percent": 71.0,
    }


def test_extract_weather_handles_missing_data():
    assert extract_weather(None) == {}
    assert extract_weather({"temp": None, "relativeHumidity": 60}) == {"humidity_percent": 60.0}


RUN_START = datetime(2026, 11, 8, 12, 32, 57, tzinfo=timezone.utc)


class FakeGarmin:
    def __init__(self, activities=None, weather=None, fail_login=False, fail_list=False, fail_weather=False):
        self.activities = activities or []
        self.weather = weather or {}
        self.fail_login, self.fail_list, self.fail_weather = fail_login, fail_list, fail_weather
        self.login_calls = []
        self.list_args = None

    def login(self, tokenstore):
        self.login_calls.append(tokenstore)
        if self.fail_login:
            raise RuntimeError("expired")

    def get_activities_by_date(self, start, end, activity_type):
        self.list_args = (start, end, activity_type)
        if self.fail_list:
            raise RuntimeError("rate limited")
        return self.activities

    def get_activity_weather(self, activity_id):
        if self.fail_weather:
            raise RuntimeError("no weather")
        return self.weather


def garmin_run():
    return {"activityId": 1000000001, "startTimeGMT": "2026-11-08 12:32:57", "distance": 20008.76, "aerobicTrainingEffect": 3.8}


def provider_for(fake):
    return GarminMetricsProvider("tokens", client_factory=lambda: fake)


def test_metrics_for_run_returns_matched_metrics_and_weather():
    fake = FakeGarmin(activities=[garmin_run()], weather={"temp": 76, "relativeHumidity": 71})

    metrics = provider_for(fake).metrics_for_run(RUN_START, 20008.0)

    assert metrics["garmin_activity_id"] == "1000000001"
    assert metrics["aerobic_training_effect"] == 3.8
    assert metrics["weather"] == {"temperature_c": 24.4, "humidity_percent": 71.0}
    assert fake.login_calls == ["tokens"]
    assert fake.list_args == ("2026-11-07", "2026-11-09", "running")


def test_metrics_for_run_returns_empty_when_no_activity_matches():
    assert provider_for(FakeGarmin(activities=[])).metrics_for_run(RUN_START, 20008.0) == {}


def test_metrics_for_run_omits_weather_when_weather_call_fails():
    fake = FakeGarmin(activities=[garmin_run()], fail_weather=True)

    metrics = provider_for(fake).metrics_for_run(RUN_START, 20008.0)

    assert "weather" not in metrics
    assert metrics["aerobic_training_effect"] == 3.8


def test_login_failure_raises_unavailable_error():
    with pytest.raises(GarminUnavailableError, match="登入失敗"):
        provider_for(FakeGarmin(fail_login=True)).metrics_for_run(RUN_START, 20008.0)


def test_activity_query_failure_raises_unavailable_error():
    with pytest.raises(GarminUnavailableError, match="活動查詢失敗"):
        provider_for(FakeGarmin(fail_list=True)).metrics_for_run(RUN_START, 20008.0)


def test_client_is_reused_and_default_factory_is_garminconnect(monkeypatch):
    fake = FakeGarmin(activities=[])
    monkeypatch.setattr("garminconnect.Garmin", lambda: fake)
    provider = GarminMetricsProvider("tokens")

    provider.metrics_for_run(RUN_START, 20008.0)
    provider.metrics_for_run(RUN_START, 20008.0)

    assert fake.login_calls == ["tokens"]