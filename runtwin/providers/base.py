from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class ProviderCapability:
    activity_list: bool
    activity_details: bool
    streams: frozenset[str]
    scheduler_safe: bool
    notes: str


class StravaDataProvider(ABC):
    """Read-only boundary for any Strava-compatible source."""

    @abstractmethod
    def capabilities(self) -> ProviderCapability:
        raise NotImplementedError

    @abstractmethod
    def list_activities(self, start: datetime | None = None, end: datetime | None = None) -> Iterable[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_activity_details(self, activity_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_activity_streams(self, activity_id: str) -> dict[str, list[Any]]:
        raise NotImplementedError
