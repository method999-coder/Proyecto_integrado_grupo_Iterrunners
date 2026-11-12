from django.db import migrations


def normalize_perfil_rol(apps, schema_editor):
    Perfil = apps.get_model("users", "Perfil")

    for perfil in Perfil.objects.select_related("usuario").all():
        usuario = perfil.usuario
        group_names = set(usuario.groups.values_list("name", flat=True))

        if usuario.is_superuser or "Admin" in group_names:
            target_rol = "admin"
        elif "Profesor" in group_names:
            target_rol = "profesor"
        else:
            target_rol = "corredor"

        if perfil.rol != target_rol:
            perfil.rol = target_rol
            perfil.save(update_fields=["rol"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0023_cumplimientoentrenamiento_comentario"),
    ]

    operations = [
        migrations.RunPython(normalize_perfil_rol, noop_reverse),
    ]
