from __future__ import annotations

import math
from typing import Any

from .schemas import EvidenceRef, WeeklyFactsSchema


def _equal(first: Any, second: Any) -> bool:
    if isinstance(first, (int, float)) and isinstance(second, (int, float)):
        return math.isclose(float(first), float(second), rel_tol=1e-6, abs_tol=1e-6)
    return first == second


def validate_evidence_value(reference: EvidenceRef, facts: WeeklyFactsSchema) -> None:
    payload = facts.model_dump(mode="json")
    if reference.activity_id:
        activity = next((item for item in payload["activity_facts"] if item["activity_id"] == reference.activity_id), None)
        if activity is None:
            raise ValueError(f"AI 報告引用 WeeklyFacts 不存在的 activity ID：{reference.activity_id}")
        if reference.metric_name not in activity:
            raise ValueError(f"活動證據欄位不存在：{reference.metric_name}")
        expected = activity[reference.metric_name]
    else:
        if reference.metric_name in payload["metrics"]:
            expected = payload["metrics"][reference.metric_name]["value"]
        elif reference.metric_name in payload["comparisons"]:
            expected = payload["comparisons"][reference.metric_name]["value"]
        elif reference.metric_name.endswith("_session_count"):
            workout_class = reference.metric_name.removesuffix("_session_count")
            if workout_class not in payload["workout_distribution"]:
                raise ValueError(f"週報證據欄位不存在：{reference.metric_name}")
            expected = payload["workout_distribution"][workout_class]["value"]
        elif reference.metric_name == "wellbeing":
            expected = {
                key: payload["wellbeing"][key]
                for key in ("fatigue", "soreness", "knee_pain")
            } if payload.get("wellbeing") else None
        else:
            raise ValueError(f"週報證據欄位不存在：{reference.metric_name}")
    if not _equal(reference.metric_value, expected):
        raise ValueError(f"AI 證據值不符：{reference.metric_name} 預期 {expected!r}，收到 {reference.metric_value!r}")
