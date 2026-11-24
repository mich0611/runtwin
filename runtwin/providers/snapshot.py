from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .base import ProviderCapability, StravaDataProvider


class SnapshotFormatError(ValueError):
    pass


class SnapshotProvider(StravaDataProvider):
    """Reads a privacy-sensitive MCP export from local disk only."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        with self.path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            payload = {"schema_version": "runtwin-mcp-snapshot-v1", "activities": payload, "streams": {}}
        if not isinstance(payload, dict) or not isinstance(payload.get("activities"), list):
            raise SnapshotFormatError("Snapshot 必須是含 activities 陣列的 JSON 物件。")
        self.payload = payload
        self._streams = {str(key): value for key, value in payload.get("streams", {}).items()}

    def capabilities(self) -> ProviderCapability:
        available = set()
        for stream in self._streams.values():
            available.update(stream.keys())
        return ProviderCapability(True, True, frozenset(available), True, "Local JSON snapshot; safe for non-interactive imports.")

    def list_activities(self, start: datetime | None = None, end: datetime | None = None) -> Iterable[dict[str, Any]]:
        for activity in self.payload["activities"]:
            start_value = activity.get("start_time") or activity.get("start_local")
            if not start_value:
                continue
            parsed = datetime.fromisoformat(start_value.replace("Z", "+00:00"))
            if start and parsed < start:
                continue
            if end and parsed > end:
                continue
            yield activity

    def get_activity_details(self, activity_id: str) -> dict[str, Any]:
        return next((item for item in self.payload["activities"] if str(item.get("id") or item.get("strava_activity_id")) == str(activity_id)), {})

    def get_activity_streams(self, activity_id: str) -> dict[str, list[Any]]:
        return self._streams.get(str(activity_id), {})
