from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from runtwin.activities.models import Activity
from runtwin.providers.strava_publish import publish_activity_analysis
from runtwin.providers.strava_write import StravaApiError, StravaConfigurationError, StravaWriteClient


class Command(BaseCommand):
    help = "將指定本機活動的分析附加到同一筆 Strava activity description。"

    def add_arguments(self, parser):
        parser.add_argument("activity_id", help="Strava activity ID（純數字）")
        parser.add_argument("--dry-run", action="store_true", help="只預覽完整 description，不送出 Strava 更新。")
        parser.add_argument("--yes", action="store_true", help="確認執行對 Strava 的寫入。")

    def handle(self, *args, **options):
        activity_id = options["activity_id"]
        try:
            activity = Activity.objects.get(strava_activity_id=activity_id)
        except Activity.DoesNotExist as exc:
            raise CommandError(f"找不到本機活動 {activity_id}。") from exc
        if not activity.analysis.strip():
            raise CommandError("活動尚無分析內容，請先同步或產生分析。")
        if not activity_id.isdigit():
            raise CommandError("Strava activity ID 必須是純數字；fixture 活動不能發布。")
        if not options["dry_run"] and not options["yes"]:
            raise CommandError("這會修改 Strava 活動描述；請加上 --yes 明確確認，或先使用 --dry-run。")

        try:
            result = publish_activity_analysis(activity, StravaWriteClient.from_settings(), dry_run=options["dry_run"])
        except (StravaConfigurationError, StravaApiError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        if options["dry_run"]:
            self.stdout.write(result["description"])
            self.stdout.write(self.style.WARNING("Dry run：未修改 Strava。"))
        else:
            activity.analysis_published_at = timezone.now()
            activity.save(update_fields=["analysis_published_at"])
            self.stdout.write(self.style.SUCCESS(f"已更新 Strava activity {activity_id} 的 description。"))
