from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0024_normalize_perfil_rol"),
    ]

    operations = [
        migrations.AddField(
            model_name="cumplimientoentrenamiento",
            name="publicar_ranking",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="cumplimientoentrenamiento",
            name="ranking_distancia",
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[(5, "5K"), (10, "10K"), (21, "21K"), (42, "42K")],
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="entrenamientodiario",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("entreno", "Entrenamiento"),
                    ("descanso", "Descanso"),
                    ("core", "Core / Fuerza"),
                    ("carrera", "Carrera"),
                    ("control", "Control"),
                ],
                default="entreno",
                max_length=20,
            ),
        ),
    ]
