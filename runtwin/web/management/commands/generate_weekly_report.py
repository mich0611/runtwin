from django.core.management.base import BaseCommand

from runtwin.ai.fallback import DeterministicFallbackProvider
from runtwin.ai.prompt_export import PromptExportProvider
from runtwin.reporting.service import generate_facts, save_validated_report
from ._common import get_athlete, resolve_week


class Command(BaseCommand):
    help = "產生確定性 fallback 週報，並可同時匯出可交給 LLM 的 prompt。"

    def add_arguments(self, parser):
        parser.add_argument("--week", help="星期一，YYYY-MM-DD")
        parser.add_argument("--export-prompt", action="store_true")

    def handle(self, *args, **options):
        athlete = get_athlete()
        week = resolve_week(options.get("week"), athlete)
        report = generate_facts(athlete, week)
        payload = DeterministicFallbackProvider().generate(report.facts_json)
        save_validated_report(report, payload, DeterministicFallbackProvider.name)
        if options["export_prompt"]:
            facts_path, prompt_path = PromptExportProvider().export(report.facts_json)
            self.stdout.write(f"Facts: {facts_path}\nPrompt: {prompt_path}")
        self.stdout.write(self.style.SUCCESS(f"Weekly report complete: {report.week_start}"))
