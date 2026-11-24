from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from .base import ProviderCapability, StravaDataProvider


class InteractiveMcpProvider(StravaDataProvider):
    """Documents MCP capability without pretending it is callable by Django jobs."""

    def capabilities(self) -> ProviderCapability:
        return ProviderCapability(
            activity_list=True,
            activity_details=True,
            streams=frozenset({"time", "distance", "heart_rate", "velocity_smooth", "altitude", "grade_smooth", "cadence", "moving", "location", "watts", "temp"}),
            scheduler_safe=False,
            notes="The authenticated MCP transport belongs to the interactive Claude client; no backend credential or supported scheduler API is available.",
        )

    def list_activities(self, start: datetime | None = None, end: datetime | None = None) -> Iterable[dict[str, Any]]:
        raise RuntimeError("Interactive Strava MCP cannot be invoked from a non-interactive Django process; import an exported snapshot instead.")

    def get_activity_details(self, activity_id: str) -> dict[str, Any]:
        raise RuntimeError("Interactive Strava MCP cannot be invoked from a non-interactive Django process; import an exported snapshot instead.")

    def get_activity_streams(self, activity_id: str) -> dict[str, list[Any]]:
        raise RuntimeError("Interactive Strava MCP cannot be invoked from a non-interactive Django process; import an exported snapshot instead.")
