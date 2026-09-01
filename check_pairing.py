import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from slideshow.models import DevicePairing
from django.contrib.auth.models import User

print('DevicePairings:', DevicePairing.objects.count())
for dp in DevicePairing.objects.all():
    print(f'User: {dp.user.email}, ID: {dp.pairing_id}')

print('\nUsers:', User.objects.count())
for user in User.objects.all():
    print(f'User: {user.email}, ID: {user.id}')
