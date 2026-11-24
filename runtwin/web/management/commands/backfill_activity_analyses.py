from __future__ import annotations

import time as time_module
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError

from runtwin.activities.models import Activity
from runtwin.activities.webhook import RUN_SPORT_TYPES, garmin_provider_from_settings, process_strava_activity
from runtwin.providers.strava_api import StravaApiProvider
from runtwin.providers.strava_write import StravaWriteClient


class Command(BaseCommand):
    help = "補抓指定日期後尚未發布分析的 Strava 跑步；可重跑，已完成項目會略過。"

    def add_arguments(self, parser):
        parser.add_argument("--since", required=True, help="起始日期（含），YYYY-MM-DD。")
        parser.add_argument("--until", help="結束日期（含），YYYY-MM-DD；預設今天。")
        parser.add_argument("--limit", type=int, default=0, help="本次最多處理筆數；0 表示不限制。")
        parser.add_argument("--retry-fallback", action="store_true", help="將 deterministic/fallback 活動重新交給 AI 模型。")
        parser.add_argument("--pause-seconds", type=float, default=1.5, help="每筆處理後暫停秒數。")
        parser.add_argument("--batch-size", type=int, default=30, help="每批最多處理筆數；預設 30，約低於 Strava 15 分鐘限制。")
        parser.add_argument("--batch-pause-seconds", type=float, default=900, help="批次間暫停秒數；預設 900。")
        parser.add_argument("--dry-run", action="store_true", help="只列出候選活動，不抓 streams、不呼叫 AI、不寫回 Strava。")

    def handle(self, *args, **options):
        try:
            since = date.fromisoformat(options["since"])
            until = date.fromisoformat(options["until"]) if options.get("until") else date.today()
        except ValueError as exc:
            raise CommandError("日期必須是 YYYY-MM-DD。") from exc
        if until < since:
            raise CommandError("--until 不可早於 --since。")

        zone = ZoneInfo("Asia/Taipei")
        start = datetime.combine(since, time.min, tzinfo=zone)
        end = datetime.combine(until, time.max, tzinfo=zone)
        limit = max(0, options["limit"])
        client = StravaWriteClient.from_settings()
        provider = StravaApiProvider(client=client)

        candidates: list[tuple[str, str, str]] = []
        for payload in provider.list_activities(start=start, end=end):
            activity_id = str(payload.get("id", ""))
            if not activity_id.isdigit() or payload.get("sport_type") not in RUN_SPORT_TYPES:
                continue
            local = Activity.objects.filter(strava_activity_id=activity_id).first()
            needs_analysis = local is None or not local.analysis.strip() or local.analysis_published_at is None
            if options["retry_fallback"] and local is not None and local.analysis_source in {"deterministic", "deterministic-fallback"}:
                needs_analysis = True
            if needs_analysis:
                candidates.append((activity_id, str(payload.get("start_date_local") or payload.get("start_date") or ""), str(payload.get("name") or "Run")))

        candidates.sort(key=lambda item: item[1])
        if limit:
            candidates = candidates[:limit]
        self.stdout.write(f"候選活動：{len(candidates)} 筆")
        for activity_id, started, name in candidates:
            self.stdout.write(f"{started} {activity_id} {name}")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run：未修改本機資料或 Strava。"))
            return

        counts = {"complete": 0, "ignored": 0, "failed": 0, "skipped": 0}
        garmin_provider = garmin_provider_from_settings()
        pause_seconds = max(0.0, options["pause_seconds"])
        batch_size = max(1, options["batch_size"])
        batch_pause_seconds = max(0.0, options["batch_pause_seconds"])
        for index, (activity_id, _, _) in enumerate(candidates, start=1):
            local = Activity.objects.filter(strava_activity_id=activity_id).first()
            if local is not None and local.analysis_published_at is None:
                Activity.objects.filter(strava_activity_id=activity_id).update(analysis_claimed_at=None)
            if options["retry_fallback"]:
                Activity.objects.filter(
                    strava_activity_id=activity_id,
                    analysis_source__in=["deterministic", "deterministic-fallback"],
                ).update(analysis_published_at=None, analysis_claimed_at=None)
            try:
                status = process_strava_activity(activity_id, client=client, garmin_provider=garmin_provider)
            except Exception as exc:
                counts["failed"] += 1
                self.stderr.write(f"[{index}/{len(candidates)}] {activity_id} failed: {type(exc).__name__}: {exc}")
            else:
                counts[status] = counts.get(status, 0) + 1
                self.stdout.write(f"[{index}/{len(candidates)}] {activity_id}: {status}")
            if index < len(candidates):
                if index % batch_size == 0 and batch_pause_seconds:
                    self.stdout.write(f"已完成 {index} 筆；暫停 {batch_pause_seconds:g} 秒以遵守 Strava rate limit。")
                    time_module.sleep(batch_pause_seconds)
                elif pause_seconds:
                    time_module.sleep(pause_seconds)

        self.stdout.write(self.style.SUCCESS(str(counts)))
