from django.core.management.base import BaseCommand, CommandError

from runtwin.ingestion.service import import_provider
from runtwin.providers.snapshot import SnapshotFormatError, SnapshotProvider


class Command(BaseCommand):
    help = "匯入由互動式 Strava MCP 匯出的本機 snapshot JSON。"

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, *args, **options):
        try:
            result = import_provider(SnapshotProvider(options["path"]), source="mcp_snapshot")
        except (OSError, SnapshotFormatError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"匯入完成：新增 {result['created']}、更新 {result['updated']}、streams {result['streams']}"))
