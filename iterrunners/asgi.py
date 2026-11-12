"""
ASGI config for iterrunners project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

# INICIO - Usar la configuración local aunque el proceso herede otro módulo
os.environ['DJANGO_SETTINGS_MODULE'] = 'iterrunners.settings'
# FIN - Usar la configuración local aunque el proceso herede otro módulo

application = get_asgi_application()
