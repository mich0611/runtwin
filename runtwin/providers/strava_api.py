from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from .base import ProviderCapability, StravaDataProvider
from .strava_write import StravaApiError, StravaWriteClient

STREAM_KEYS = frozenset({
    "time",
    "distance",
    "heartrate",
    "velocity_smooth",
    "altitude",
    "grade_smooth",
    "cadence",
    "moving",
    "latlng",
})


class StravaApiProvider(StravaDataProvider):
    """Read Strava activities through the same rotating OAuth token store used for writes."""

    def __init__(self, client: StravaWriteClient | None = None, activity_ids: Iterable[str] | None = None):
        self.client = client or StravaWriteClient.from_settings()
        self.activity_ids = tuple(str(value) for value in activity_ids) if activity_ids is not None else None
        self._activity_cache: dict[str, dict[str, Any]] = {}

    def capabilities(self) -> ProviderCapability:
        return ProviderCapability(True, True, STREAM_KEYS, True, "Strava API v3 with refresh-token rotation.")

    def list_activities(self, start: datetime | None = None, end: datetime | None = None) -> Iterable[dict[str, Any]]:
        if self.activity_ids is not None:
            for activity_id in self.activity_ids:
                yield self.get_activity_details(activity_id)
            return

        params: dict[str, str | int] = {"per_page": 100}
        if start:
            params["after"] = _timestamp(start)
        if end:
            params["before"] = _timestamp(end)
        page = 1
        while True:
            activities = self.client.list_activities(params={**params, "page": page})
            yield from activities
            if len(activities) < 100:
                break
            page += 1

    def get_activity_details(self, activity_id: str) -> dict[str, Any]:
        key = str(activity_id)
        if key not in self._activity_cache:
            self._activity_cache[key] = self.client.get_activity(key)
        return self._activity_cache[key]

    def get_activity_streams(self, activity_id: str) -> dict[str, list[Any]]:
        try:
            streams = self.client.get_activity_streams(activity_id)
        except StravaApiError as exc:
            if exc.status_code == 404:
                return {}
            raise
        normalized: dict[str, list[Any]] = {}
        for key, value in streams.items():
            if isinstance(value, dict):
                value = value.get("data")
            if isinstance(value, list):
                normalized[key] = value
        return normalized


def _timestamp(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp())
