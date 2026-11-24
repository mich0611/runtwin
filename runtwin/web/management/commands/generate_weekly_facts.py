from django.core.management.base import BaseCommand

from runtwin.reporting.service import generate_facts
from ._common import get_athlete, resolve_week


class Command(BaseCommand):
    help = "計算上一完整週期或指定週的 WeeklyFacts。"

    def add_arguments(self, parser):
        parser.add_argument("--week", help="星期一，YYYY-MM-DD")

    def handle(self, *args, **options):
        athlete = get_athlete()
        week = resolve_week(options.get("week"), athlete)
        report = generate_facts(athlete, week)
        self.stdout.write(self.style.SUCCESS(f"WeeklyFacts ready: {report.week_start}"))
