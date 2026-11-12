from django.db import migrations, models


def seed_default_club(apps, schema_editor):
    Club = apps.get_model('users', 'Club')
    Grupo = apps.get_model('users', 'Grupo')

    # Create the initial kinerrunners club
    default_club, created = Club.objects.get_or_create(nombre='kinerrunners', defaults={'descripcion': 'Club inicial (kinerrunners) creado automáticamente'})

    # Assign existing groups to the default club if they have no club
    Grupo.objects.filter(club__isnull=True).update(club=default_club)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0038_perfil_last_seen'),
    ]

    operations = [
        migrations.CreateModel(
            name='Club',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
                ('descripcion', models.CharField(blank=True, max_length=300)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['nombre']},
        ),
        migrations.AddField(
            model_name='grupo',
            name='club',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='grupos', to='users.club'),
        ),
        migrations.RunPython(seed_default_club, reverse_code=migrations.RunPython.noop),
    ]
