from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from runtwin.ingestion.service import import_provider
from runtwin.providers.mcp import InteractiveMcpProvider
from runtwin.providers.strava_api import StravaApiProvider


class Command(BaseCommand):
    help = "透過可程式化 provider 同步 Strava；目前不支援互動式 MCP 排程。"

    def handle(self, *args, **options):
        provider_name = settings.RUNTWIN_PROVIDER
        if provider_name == "mcp":
            provider = InteractiveMcpProvider()
        elif provider_name == "strava_api":
            provider = StravaApiProvider()
        else:
            raise CommandError("RUNTWIN_PROVIDER=snapshot 時請使用 import_mcp_snapshot <path>。互動式 MCP 無法由排程安全呼叫。")
        try:
            result = import_provider(provider, source=provider_name)
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(str(result)))
