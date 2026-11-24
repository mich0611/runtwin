from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activities", "0003_activity_analysis"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="analysis_generated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="analysis_published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="analysis_source",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="activity",
            name="analysis_version",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.CreateModel(
            name="StravaWebhookEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subscription_id", models.BigIntegerField()),
                ("object_type", models.CharField(max_length=16)),
                ("object_id", models.BigIntegerField()),
                ("aspect_type", models.CharField(max_length=16)),
                ("owner_id", models.BigIntegerField()),
                ("event_time", models.BigIntegerField()),
                ("updates", models.JSONField(default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "等待處理"),
                            ("processing", "處理中"),
                            ("complete", "完成"),
                            ("ignored", "已忽略"),
                            ("failed", "失敗"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["received_at"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("subscription_id", "object_type", "object_id", "aspect_type", "event_time"),
                        name="unique_strava_webhook_delivery",
                    )
                ],
            },
        ),
    ]
