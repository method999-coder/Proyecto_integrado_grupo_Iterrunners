from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0025_entrenamientodiario_tipo_extra_and_ranking_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="cumplimientoentrenamiento",
            name="publicar_feed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="cumplimientoentrenamiento",
            name="strava_actividad",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cumplimientos_feed", to="users.stravaactividad"),
        ),
    ]
