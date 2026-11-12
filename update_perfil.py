#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iterrunners.settings')
django.setup()

from users.models import Perfil

# Actualizar el primer perfil (Catalina)
p = Perfil.objects.first()
if p:
    print(f"Antes: nombre='{p.nombre}', apellido='{p.apellido}'")
    
    # El nombre actual es "Catalina  Manriques Becerra"
    # Lo dividimos
    p.nombre = "Catalina"
    p.apellido = "Manriques Becerra"
    p.save()
    
    print(f"Después: nombre='{p.nombre}', apellido='{p.apellido}'")
    print("✅ Perfil actualizado exitosamente")
else:
    print("❌ No se encontró ningún perfil")
