from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .garmin_match import match_garmin_activity

GARMIN_METRICS_VERSION = "garmin-metrics-v1"


class GarminUnavailableError(RuntimeError):
    """Garmin supplementary data could not be fetched; callers continue without it."""

ACTIVITY_FIELDS = {
    "aerobicTrainingEffect": "aerobic_training_effect",
    "anaerobicTrainingEffect": "anaerobic_training_effect",
    "trainingEffectLabel": "training_effect_label",
    "activityTrainingLoad": "training_load",
    "avgGroundContactTime": "ground_contact_time_ms",
    "avgVerticalOscillation": "vertical_oscillation_cm",
    "avgStrideLength": "stride_length_cm",
    "normPower": "normalized_power_w",
    "differenceBodyBattery": "body_battery_change",
    "vO2MaxValue": "vo2max",
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), 2)


def extract_activity_metrics(item: dict[str, Any]) -> dict[str, Any]:
    """Keep the Garmin-only activity metrics RunTwin uses, under stable keys."""
    metrics: dict[str, Any] = {}
    for source, target in ACTIVITY_FIELDS.items():
        value = item.get(source)
        if isinstance(value, str) and value:
            metrics[target] = value
        elif _number(value) is not None:
            metrics[target] = _number(value)
    zones = {}
    for zone in range(1, 6):
        seconds = _number(item.get(f"hrTimeInZone_{zone}"))
        if seconds is not None:
            zones[str(zone)] = seconds
    if zones:
        metrics["hr_zone_seconds"] = zones
    return metrics


def _fahrenheit_to_celsius(value: Any) -> float | None:
    number = _number(value)
    return round((number - 32) * 5 / 9, 1) if number is not None else None


def extract_weather(weather: Any) -> dict[str, Any]:
    """Garmin weather temperatures are Fahrenheit regardless of account units."""
    if not isinstance(weather, dict):
        return {}
    result = {
        "temperature_c": _fahrenheit_to_celsius(weather.get("temp")),
        "apparent_temperature_c": _fahrenheit_to_celsius(weather.get("apparentTemp")),
        "dew_point_c": _fahrenheit_to_celsius(weather.get("dewPoint")),
        "humidity_percent": _number(weather.get("relativeHumidity")),
    }
    return {key: value for key, value in result.items() if value is not None}



class GarminMetricsProvider:
    """Read-only Garmin Connect access that reuses the tokens created by garmin-mcp-auth."""

    def __init__(self, token_dir: str, client_factory: Callable[[], Any] | None = None):
        self.token_dir = token_dir
        self.client_factory = client_factory
        self._client: Any | None = None

    def _connected(self) -> Any:
        if self._client is None:
            try:
                if self.client_factory is None:
                    from garminconnect import Garmin

                    self.client_factory = Garmin
                client = self.client_factory()
                client.login(self.token_dir)
            except Exception as exc:
                raise GarminUnavailableError(f"Garmin 登入失敗：{type(exc).__name__}") from exc
            self._client = client
        return self._client

    def metrics_for_run(self, start_time: datetime, distance_m: float) -> dict[str, Any]:
        """Return Garmin metrics for the run matching a Strava start time, or {} if none matches."""
        client = self._connected()
        day = start_time.astimezone(timezone.utc).date()
        try:
            candidates = client.get_activities_by_date(
                (day - timedelta(days=1)).isoformat(), (day + timedelta(days=1)).isoformat(), "running"
            )
        except Exception as exc:
            raise GarminUnavailableError(f"Garmin 活動查詢失敗：{type(exc).__name__}") from exc
        match = match_garmin_activity(start_time, distance_m, candidates or [])
        if match is None:
            return {}
        metrics = {
            "version": GARMIN_METRICS_VERSION,
            "garmin_activity_id": str(match.get("activityId")),
            **extract_activity_metrics(match),
        }
        try:
            weather = extract_weather(client.get_activity_weather(str(match.get("activityId"))))
        except Exception:
            weather = {}
        if weather:
            metrics["weather"] = weather
        return metrics