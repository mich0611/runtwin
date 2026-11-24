from django.db import models

from runtwin.activities.models import Activity
from runtwin.athletes.models import AthleteProfile


class GenerationStatus(models.TextChoices):
    FACTS_READY = "facts_ready", "數據已完成"
    COMPLETE = "complete", "報告已完成"
    PENDING_AI = "pending_ai", "等待 AI 匯入"
    FAILED = "failed", "失敗"


class WeeklyReport(models.Model):
    athlete = models.ForeignKey(AthleteProfile, on_delete=models.CASCADE, related_name="weekly_reports")
    week_start = models.DateField()
    week_end = models.DateField()
    facts_json = models.JSONField(default=dict)
    report_json = models.JSONField(default=dict)
    rendered_summary = models.TextField(blank=True)
    generation_status = models.CharField(max_length=24, choices=GenerationStatus.choices, default=GenerationStatus.FACTS_READY)
    error_message = models.TextField(blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    model_name = models.CharField(max_length=128, blank=True)
    report_version = models.CharField(max_length=32, default="weekly-report-v1")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["athlete", "week_start"], name="unique_athlete_week_report")]
        ordering = ["-week_start"]

    def __str__(self) -> str:
        return f"{self.week_start}–{self.week_end} 週報"


class ProgressNarrative(models.Model):
    fingerprint = models.CharField(max_length=64, unique=True)
    model_version = models.CharField(max_length=64)
    source = models.CharField(max_length=64)
    narrative = models.TextField()
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self) -> str:
        return f"{self.model_version} ({self.source})"


class InsightEvidence(models.Model):
    weekly_report = models.ForeignKey(WeeklyReport, on_delete=models.CASCADE, related_name="evidence")
    insight_key = models.CharField(max_length=128)
    activity = models.ForeignKey(Activity, on_delete=models.SET_NULL, null=True, blank=True, related_name="insight_evidence")
    metric_name = models.CharField(max_length=128)
    metric_value = models.JSONField(default=dict)
    explanation = models.TextField()

    class Meta:
        ordering = ["insight_key", "id"]

    def __str__(self) -> str:
        return f"{self.insight_key}: {self.metric_name}"
