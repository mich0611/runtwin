from django.core.management.base import BaseCommand

from runtwin.athletes.models import AthleteProfile


class Command(BaseCommand):
    help = "建立不含個人資料、可於 admin 修改的 AthleteProfile。"

    def handle(self, *args, **options):
        defaults = {
            "timezone": "Asia/Taipei",
            "half_marathon_pb": None,
            "half_marathon_goal": None,
            "marathon_goal": None,
            "normal_weekly_distance": 0,
            "runs_per_week": "",
            "weekday_distance_limit": 0,
            "preferred_long_run_days": [],
            "provisional_tempo_hr_low": None,
            "provisional_tempo_hr_high": None,
            "observed_hr_max": None,
            "garmin_vo2max_reference_low": None,
            "garmin_vo2max_reference_high": None,
            "notes": "",
        }
        athlete = AthleteProfile.objects.order_by("id").first()
        if athlete:
            created = False
        else:
            athlete = AthleteProfile.objects.create(**defaults)
            created = True
        action = "created" if created else "already exists; unchanged"
        self.stdout.write(self.style.SUCCESS(f"AthleteProfile {action}: id={athlete.id}"))
