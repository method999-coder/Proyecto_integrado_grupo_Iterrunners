#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iterrunners.settings')
django.setup()

from users.models import Perfil

p = Perfil.objects.first()
print(f"nombre=[{p.nombre}]")
print(f"apellido=[{p.apellido}]")
print(f"len(apellido)={len(p.apellido)}")
print(f"repr(apellido)={repr(p.apellido)}")
