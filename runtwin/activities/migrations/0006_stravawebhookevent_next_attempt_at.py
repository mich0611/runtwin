from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activities", "0005_stravawebhookevent_claimed_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="stravawebhookevent",
            name="next_attempt_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
