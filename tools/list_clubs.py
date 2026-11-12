import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','iterrunners.settings')
import django
django.setup()
from users.models import Club
print(list(Club.objects.values_list('id','nombre')))
