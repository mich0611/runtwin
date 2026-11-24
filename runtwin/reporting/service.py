from __future__ import annotations

from datetime import date
from typing import Any

from django.db import transaction
from django.utils import timezone

from runtwin.activities.models import Activity
from runtwin.athletes.models import AthleteProfile
from .facts import build_weekly_facts
from .models import GenerationStatus, InsightEvidence, WeeklyReport
from .periods import normalize_week_start
from .schemas import AIReportSchema, WeeklyFactsSchema


@transaction.atomic
def generate_facts(athlete: AthleteProfile, week_start: date) -> WeeklyReport:
    week_start = normalize_week_start(week_start)
    report, _ = WeeklyReport.objects.get_or_create(
        athlete=athlete,
        week_start=week_start,
        defaults={"week_end": week_start + date.resolution * 6, "generation_status": GenerationStatus.FACTS_READY},
    )
    try:
        facts = build_weekly_facts(athlete, week_start)
    except Exception as exc:
        report.generation_status = GenerationStatus.FAILED
        report.error_message = f"{type(exc).__name__}: {exc}"[:4000]
        report.save(update_fields=["generation_status", "error_message"])
        raise
    report.week_end = date.fromisoformat(facts["week_end"])
    report.facts_json = facts
    report.generation_status = GenerationStatus.FACTS_READY
    report.error_message = ""
    report.save()
    return report


@transaction.atomic
def save_validated_report(report: WeeklyReport, payload: dict[str, Any], model_name: str) -> WeeklyReport:
    try:
        facts = WeeklyFactsSchema.model_validate(report.facts_json)
        validated = AIReportSchema.model_validate(payload)
        validated.validate_evidence_against(facts)
    except Exception as exc:
        report.generation_status = GenerationStatus.FAILED
        report.error_message = f"{type(exc).__name__}: {exc}"[:4000]
        report.save(update_fields=["generation_status", "error_message"])
        raise
    data = validated.model_dump(mode="json")
    report.report_json = data
    report.rendered_summary = validated.executive_summary
    report.generation_status = GenerationStatus.COMPLETE
    report.generated_at = timezone.now()
    report.model_name = model_name
    report.error_message = ""
    report.save()

    InsightEvidence.objects.filter(weekly_report=report).delete()
    valid_activities = {item.strava_activity_id: item for item in Activity.objects.filter(strava_activity_id__in={ref.activity_id for ref in facts.activities})}
    for group_name in ("positives", "concerns", "goal_gap"):
        for index, item in enumerate(data[group_name]):
            key = f"{group_name}.{index}"
            for evidence in item["evidence"]:
                InsightEvidence.objects.create(
                    weekly_report=report,
                    insight_key=key,
                    activity=valid_activities.get(evidence.get("activity_id")),
                    metric_name=evidence["metric_name"],
                    metric_value={"value": evidence["metric_value"]},
                    explanation=item["reasoning"],
                )
    return report
