from django.db import models


class AthleteProfile(models.Model):
    timezone = models.CharField(max_length=64, default="Asia/Taipei")
    half_marathon_pb = models.DurationField(null=True, blank=True)
    half_marathon_goal = models.DurationField(null=True, blank=True)
    marathon_goal = models.DurationField(null=True, blank=True)
    normal_weekly_distance = models.DecimalField(max_digits=6, decimal_places=1, default=0, help_text="公里")
    runs_per_week = models.CharField(max_length=16, default="")
    weekday_distance_limit = models.DecimalField(max_digits=5, decimal_places=1, default=0, help_text="公里")
    preferred_long_run_days = models.JSONField(default=list)
    provisional_tempo_hr_low = models.PositiveSmallIntegerField(null=True, blank=True)
    provisional_tempo_hr_high = models.PositiveSmallIntegerField(null=True, blank=True)
    observed_hr_max = models.PositiveSmallIntegerField(null=True, blank=True)
    garmin_vo2max_reference_low = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    garmin_vo2max_reference_high = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"跑者設定（{self.timezone}）"


class WellbeingCheckIn(models.Model):
    athlete = models.ForeignKey(AthleteProfile, on_delete=models.CASCADE, related_name="check_ins")
    week_start = models.DateField()
    sleep_quality = models.PositiveSmallIntegerField()
    fatigue = models.PositiveSmallIntegerField()
    soreness = models.PositiveSmallIntegerField()
    knee_pain = models.PositiveSmallIntegerField()
    motivation = models.PositiveSmallIntegerField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["athlete", "week_start"], name="unique_athlete_week_checkin")]
        ordering = ["-week_start"]

    def __str__(self) -> str:
        return f"{self.week_start} 主觀狀態"
