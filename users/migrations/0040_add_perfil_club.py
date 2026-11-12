from django.db import migrations, models


def copy_perfil_club(apps, schema_editor):
    Perfil = apps.get_model('users', 'Perfil')
    Grupo = apps.get_model('users', 'Grupo')

    for perfil in Perfil.objects.select_related('grupo'):
        try:
            if perfil.grupo and getattr(perfil.grupo, 'club', None):
                perfil.club = perfil.grupo.club
                perfil.save(update_fields=['club'])
        except Exception:
            # ignore individual failures to avoid blocking migration
            continue


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0039_add_club'),
    ]

    operations = [
        migrations.AddField(
            model_name='perfil',
            name='club',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='perfiles', to='users.club'),
        ),
        migrations.RunPython(copy_perfil_club, reverse_code=migrations.RunPython.noop),
    ]
