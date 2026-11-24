from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "安全重算指定週報（upsert，不新增重複週）。"

    def add_arguments(self, parser):
        parser.add_argument("--week", required=True, help="星期一，YYYY-MM-DD")
        parser.add_argument("--export-prompt", action="store_true")

    def handle(self, *args, **options):
        call_command("generate_weekly_report", week=options["week"], export_prompt=options["export_prompt"])
