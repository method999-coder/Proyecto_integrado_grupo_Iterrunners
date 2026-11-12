from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0027_feedcomentario_feedlike"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name="cumplimientoentrenamiento",
            name="publicar_feed",
        ),
        migrations.RemoveField(
            model_name="cumplimientoentrenamiento",
            name="strava_actividad",
        ),
        migrations.DeleteModel(
            name="FeedComentario",
        ),
        migrations.DeleteModel(
            name="FeedLike",
        ),
        migrations.CreateModel(
            name="FeedLike",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actividad", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feed_likes", to="users.stravaactividad")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feed_likes", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
                "unique_together": {("actividad", "usuario")},
            },
        ),
        migrations.CreateModel(
            name="FeedComentario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("texto", models.CharField(max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actividad", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feed_comentarios", to="users.stravaactividad")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feed_comentarios", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
    ]
