from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activities", "0006_stravawebhookevent_next_attempt_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="analysis_claimed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
