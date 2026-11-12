from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0028_auto_feed_from_strava"),
    ]

    operations = [
        migrations.AddField(
            model_name="stravaactividad",
            name="publicar_en_feed",
            field=models.BooleanField(default=False),
        ),
    ]
