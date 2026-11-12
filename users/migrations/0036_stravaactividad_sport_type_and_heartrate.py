from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0035_entrenamientodiario_modalidad"),
    ]

    operations = [
        migrations.AddField(
            model_name="stravaactividad",
            name="sport_type",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="stravaactividad",
            name="average_heartrate",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stravaactividad",
            name="max_heartrate",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
