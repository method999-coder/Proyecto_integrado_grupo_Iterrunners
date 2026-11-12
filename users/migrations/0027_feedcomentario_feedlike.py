from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0026_cumplimientoentrenamiento_publicar_feed_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FeedComentario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("texto", models.CharField(max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("cumplimiento", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feed_comentarios", to="users.cumplimientoentrenamiento")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feed_comentarios", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.CreateModel(
            name="FeedLike",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("cumplimiento", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feed_likes", to="users.cumplimientoentrenamiento")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feed_likes", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
                "unique_together": {("cumplimiento", "usuario")},
            },
        ),
    ]
