#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iterrunners.settings')
django.setup()

from users.models import Perfil
from django.contrib.auth.models import User

# Obtener el primer usuario
user = User.objects.first()
print(f"Usuario: {user.username}")

# Obtener el perfil
perfil = Perfil.objects.filter(usuario=user).first()

print(f"\nAtributos del objeto Perfil:")
print(f"  id: {perfil.id}")
print(f"  usuario_id: {perfil.usuario_id}")
print(f"  nombre: [{perfil.nombre}]")
print(f"  apellido: [{perfil.apellido}]")
print(f"  apellido type: {type(perfil.apellido)}")
print(f"  apellido len: {len(perfil.apellido)}")

print(f"\nDatos crudos del ORM:")
for field in Perfil._meta.get_fields():
    if field.name == 'apellido':
        print(f"  Campo apellido existe en modelo")
        value = getattr(perfil, field.name)
        print(f"    Valor: [{value}]")

print(f"\nIntentando acceso directo a __dict__:")
print(f"  {perfil.__dict__}")
