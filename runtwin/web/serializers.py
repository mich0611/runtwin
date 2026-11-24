from rest_framework import serializers

from runtwin.activities.models import Activity
from runtwin.reporting.models import WeeklyReport


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        exclude = ["raw_summary"]


class WeeklyReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeeklyReport
        fields = ["week_start", "week_end", "facts_json", "report_json", "rendered_summary", "generation_status", "generated_at", "model_name", "report_version"]
