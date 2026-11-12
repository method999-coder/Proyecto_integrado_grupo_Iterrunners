"""
WSGI config for iterrunners project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# INICIO - Usar la configuración local aunque el proceso herede otro módulo
os.environ['DJANGO_SETTINGS_MODULE'] = 'iterrunners.settings'
# FIN - Usar la configuración local aunque el proceso herede otro módulo

application = get_wsgi_application()
