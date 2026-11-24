from django.core.management.base import BaseCommand

from runtwin.ai.progress import get_progress_narrative
from runtwin.progress.analysis import build_progress_analysis


class Command(BaseCommand):
    help = "依目前進步因素模型產生或取得快取的 AI 白話摘要。"

    def handle(self, *args, **options):
        progress = build_progress_analysis()
        result = get_progress_narrative(progress, generate=True)
        self.stdout.write(result["text"])
        self.stdout.write(self.style.SUCCESS(f"Progress narrative ready: {result['source']}"))
