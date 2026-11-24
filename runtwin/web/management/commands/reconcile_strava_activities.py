from django.conf import settings
from django.core.management.base import BaseCommand

from runtwin.activities.webhook import reconcile_recent_strava_runs


class Command(BaseCommand):
    help = "掃描近期 Strava 跑步，補做遺漏的分析與 description 回填。"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None, help="回看天數，預設 STRAVA_RECONCILE_DAYS。")
        parser.add_argument("--limit", type=int, default=100, help="最多處理幾筆未回填跑步，預設 100。")

    def handle(self, *args, **options):
        days = options["days"] if options["days"] is not None else settings.STRAVA_RECONCILE_DAYS
        result = reconcile_recent_strava_runs(days=max(1, days), limit=max(1, options["limit"]))
        self.stdout.write(self.style.SUCCESS(str(result)))
