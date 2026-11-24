from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Confidence = Literal["low", "medium", "high"]
MetricStatus = Literal["ok", "insufficient_data"]


class Metric(BaseModel):
    value: Any = None
    unit: str
    sample_size: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    confidence: Confidence
    calculation_version: str
    status: MetricStatus = "ok"


class ActivityReference(BaseModel):
    activity_id: str
    date: str
    name: str


class WeeklyFactsSchema(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: str
    calculation_version: str
    week_start: str
    week_end: str
    athlete_profile: dict[str, Any]
    metrics: dict[str, Metric]
    comparisons: dict[str, Metric]
    trends: dict[str, Any]
    workout_distribution: dict[str, Metric]
    activities: list[ActivityReference]
    activity_facts: list[dict[str, Any]]
    quality: dict[str, Any]
    wellbeing: dict[str, Any] | None = None


class EvidenceRef(BaseModel):
    metric_name: str
    metric_value: Any
    activity_id: str | None = None
    date: str | None = None
    activity_name: str | None = None


class InsightItem(BaseModel):
    claim: str
    evidence: list[EvidenceRef]
    confidence: Confidence
    reasoning: str
    related_activity_ids: list[str] = Field(default_factory=list)

    @field_validator("related_activity_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(str(item) for item in value))


class SuggestedSession(BaseModel):
    day: str
    purpose: str
    warmup: str
    main_set: str
    cooldown: str
    intensity: str
    evidence: str
    fallback: str


class AIReportSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    executive_summary: str
    weekly_snapshot: list[str]
    positives: list[InsightItem] = Field(max_length=3)
    concerns: list[InsightItem] = Field(max_length=3)
    goal_gap: list[InsightItem]
    next_week_priority: str
    suggested_sessions: list[SuggestedSession] = Field(min_length=4, max_length=5)
    recovery_note: str
    data_limitations: list[str]

    def validate_evidence_against(self, facts: WeeklyFactsSchema) -> None:
        from .evidence import validate_evidence_value

        valid_ids = {activity.activity_id for activity in facts.activities}
        for group in (self.positives, self.concerns, self.goal_gap):
            for item in group:
                invalid = set(item.related_activity_ids) - valid_ids
                invalid.update(ref.activity_id for ref in item.evidence if ref.activity_id and ref.activity_id not in valid_ids)
                if invalid:
                    raise ValueError(f"AI 報告引用 WeeklyFacts 不存在的 activity ID：{sorted(invalid)}")
                evidence_ids = {ref.activity_id for ref in item.evidence if ref.activity_id}
                if set(item.related_activity_ids) != evidence_ids:
                    raise ValueError("related_activity_ids 必須與 evidence 中的 activity_id 完全一致。")
                for reference in item.evidence:
                    validate_evidence_value(reference, facts)
