from __future__ import annotations

import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from runtwin.activities.webhook import process_pending_webhook_events, reconcile_recent_strava_runs


class Command(BaseCommand):
    help = "處理已接收的 Strava webhook；預設常駐輪詢，--once 只執行一批。"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="處理一批後結束。")
        parser.add_argument("--limit", type=int, default=20, help="每批最多處理事件數。")

    def handle(self, *args, **options):
        once = options["once"]
        limit = max(1, options["limit"])
        next_reconcile_at = 0.0
        while True:
            close_old_connections()
            try:
                result = process_pending_webhook_events(limit=limit)
            except Exception as exc:
                self.stderr.write(f"webhook processing failed: {type(exc).__name__}: {exc}")
            else:
                if any(result.values()):
                    self.stdout.write(str(result))
            now = time.monotonic()
            if now >= next_reconcile_at:
                try:
                    reconciled = reconcile_recent_strava_runs(days=settings.STRAVA_RECONCILE_DAYS, limit=limit)
                except Exception as exc:
                    self.stderr.write(f"reconcile failed: {type(exc).__name__}: {exc}")
                else:
                    if any(reconciled.values()):
                        self.stdout.write(f"reconcile: {reconciled}")
                next_reconcile_at = now + max(60, settings.STRAVA_RECONCILE_INTERVAL_SECONDS)
            if once:
                return
            time.sleep(max(1, settings.STRAVA_WEBHOOK_POLL_SECONDS))
