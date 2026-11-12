from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0037_lactatomanual"),
    ]

    operations = [
        migrations.AddField(
            model_name="perfil",
            name="last_seen",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
