from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activities", "0008_alter_activity_workout_class"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="garmin_metrics",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
