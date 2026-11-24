import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from runtwin.reporting.models import WeeklyReport
from runtwin.reporting.service import save_validated_report
from runtwin.reporting.schemas import AIReportSchema, WeeklyFactsSchema


class Command(BaseCommand):
    help = "驗證並匯入 LLM 產生的固定 schema JSON 報告。"

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--week", required=True, help="星期一，YYYY-MM-DD")
        parser.add_argument("--model-name", default="manual-ai-import")

    def handle(self, *args, **options):
        report = WeeklyReport.objects.filter(week_start=options["week"]).first()
        if not report:
            raise CommandError("找不到該週 WeeklyFacts；請先執行 generate_weekly_facts。")
        try:
            payload = json.loads(Path(options["path"]).read_text(encoding="utf-8"))
            save_validated_report(report, payload, options["model_name"])
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"AI report imported: {report.week_start}"))
