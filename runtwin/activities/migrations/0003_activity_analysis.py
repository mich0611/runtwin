from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activities", "0002_datasyncrun"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="analysis",
            field=models.TextField(blank=True),
        ),
    ]
