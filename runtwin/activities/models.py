from django.db import models


class WorkoutClass(models.TextChoices):
    EASY = "easy", "輕鬆跑"
    RECOVERY = "recovery", "恢復跑"
    LONG = "long", "長跑"
    TEMPO_THRESHOLD = "tempo_threshold", "節奏／閾值"
    TEMPO = "tempo", "節奏跑"
    THRESHOLD = "threshold", "閾值跑"
    FARTLEK = "fartlek", "法特雷克"
    INTERVAL = "interval", "間歇"
    PROGRESSION = "progression", "漸速跑"
    RACE = "race", "比賽"
    UNKNOWN = "unknown", "未知"


class Activity(models.Model):
    strava_activity_id = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_time = models.DateTimeField(db_index=True)
    sport_type = models.CharField(max_length=32)
    distance = models.FloatField(help_text="公尺")
    moving_time = models.PositiveIntegerField(help_text="秒")
    elapsed_time = models.PositiveIntegerField(help_text="秒")
    elevation_gain = models.FloatField(default=0, help_text="公尺")
    average_hr = models.FloatField(null=True, blank=True)
    max_hr = models.FloatField(null=True, blank=True)
    average_pace = models.FloatField(null=True, blank=True, help_text="秒／公里")
    workout_class = models.CharField(max_length=32, choices=WorkoutClass.choices, default=WorkoutClass.UNKNOWN)
    classification_confidence = models.FloatField(default=0)
    classification_reasons = models.JSONField(default=list)
    classifier_version = models.CharField(max_length=32, default="rules-v1")
    source = models.CharField(max_length=32, default="snapshot")
    data_quality_score = models.FloatField(default=0)
    quality_issues = models.JSONField(default=list)
    quality_version = models.CharField(max_length=32, default="quality-v1")
    has_hr_stream = models.BooleanField(default=False)
    has_pace_stream = models.BooleanField(default=False)
    has_altitude_stream = models.BooleanField(default=False)
    stream_features = models.JSONField(default=dict)
    raw_summary = models.JSONField(default=dict)
    garmin_metrics = models.JSONField(default=dict, blank=True)
    analysis = models.TextField(blank=True)
    analysis_source = models.CharField(max_length=64, blank=True)
    analysis_version = models.CharField(max_length=64, blank=True)
    analysis_generated_at = models.DateTimeField(null=True, blank=True)
    analysis_published_at = models.DateTimeField(null=True, blank=True)
    analysis_claimed_at = models.DateTimeField(null=True, blank=True)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_time"]

    def __str__(self) -> str:
        return f"{self.start_time:%Y-%m-%d} {self.name}"


class DataSyncRun(models.Model):
    source = models.CharField(max_length=32)
    range_start = models.DateTimeField(null=True, blank=True)
    range_end = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, default="running")
    activities_created = models.PositiveIntegerField(default=0)
    activities_updated = models.PositiveIntegerField(default=0)
    streams_imported = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.source} {self.status} {self.started_at:%Y-%m-%d %H:%M}"


class ActivityStream(models.Model):
    activity = models.OneToOneField(Activity, on_delete=models.CASCADE, related_name="stream")
    time = models.JSONField(default=list)
    distance = models.JSONField(default=list)
    heart_rate = models.JSONField(default=list)
    velocity = models.JSONField(default=list)
    altitude = models.JSONField(default=list)
    grade = models.JSONField(default=list)
    cadence = models.JSONField(default=list)
    moving = models.JSONField(default=list)
    gps = models.JSONField(default=list)
    sample_count = models.PositiveIntegerField(default=0)
    source_resolution = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.activity_id} streams ({self.sample_count})"


class StravaWebhookEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "等待處理"
        PROCESSING = "processing", "處理中"
        COMPLETE = "complete", "完成"
        IGNORED = "ignored", "已忽略"
        FAILED = "failed", "失敗"

    subscription_id = models.BigIntegerField()
    object_type = models.CharField(max_length=16)
    object_id = models.BigIntegerField()
    aspect_type = models.CharField(max_length=16)
    owner_id = models.BigIntegerField()
    event_time = models.BigIntegerField()
    updates = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["received_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription_id", "object_type", "object_id", "aspect_type", "event_time"],
                name="unique_strava_webhook_delivery",
            )
        ]

    def __str__(self) -> str:
        return f"{self.object_type}/{self.object_id} {self.aspect_type} ({self.status})"
