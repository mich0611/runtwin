from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ReportProvider(ABC):
    name = "abstract"

    @abstractmethod
    def generate(self, facts: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
