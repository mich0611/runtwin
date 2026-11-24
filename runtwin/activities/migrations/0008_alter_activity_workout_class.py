from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activities", "0007_activity_analysis_claimed_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="activity",
            name="workout_class",
            field=models.CharField(
                choices=[
                    ("easy", "輕鬆跑"),
                    ("recovery", "恢復跑"),
                    ("long", "長跑"),
                    ("tempo_threshold", "節奏／閾值"),
                    ("tempo", "節奏跑"),
                    ("threshold", "閾值跑"),
                    ("fartlek", "法特雷克"),
                    ("interval", "間歇"),
                    ("progression", "漸速跑"),
                    ("race", "比賽"),
                    ("unknown", "未知"),
                ],
                default="unknown",
                max_length=32,
            ),
        ),
    ]
