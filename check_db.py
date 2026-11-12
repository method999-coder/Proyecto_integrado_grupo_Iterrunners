#!/usr/bin/env python
import os
import django
import sqlite3

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iterrunners.settings')
django.setup()

# Conectar directamente a SQLite
conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

# Ver la estructura de la tabla users_perfil
cursor.execute("PRAGMA table_info(users_perfil)")
columns = cursor.fetchall()

print("Columnas en tabla users_perfil:")
for col in columns:
    print(f"  {col[1]} ({col[2]})")

# Ver datos del primer perfil
cursor.execute("SELECT nombre, apellido FROM users_perfil LIMIT 1")
result = cursor.fetchone()
if result:
    print(f"\nDatos del primer perfil:")
    print(f"  nombre=[{result[0]}]")
    print(f"  apellido=[{result[1]}]")
else:
    print("\nNo hay perfiles")

conn.close()
