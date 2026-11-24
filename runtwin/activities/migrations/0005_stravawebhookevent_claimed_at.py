from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activities", "0004_activity_analysis_metadata_and_webhooks"),
    ]

    operations = [
        migrations.AddField(
            model_name="stravawebhookevent",
            name="claimed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
