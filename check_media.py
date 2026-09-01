import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from slideshow.models import MediaFile
from django.contrib.auth.models import User

print('Media Files:', MediaFile.objects.count())
for mf in MediaFile.objects.all():
    user = mf.user
    user_email = user.email if user else 'None'
    user_id = user.id if user else 'None'
    print(f'File: {mf.title}, User: {user_email}, User ID: {user_id}')

print('\nUsers:')
for user in User.objects.all():
    print(f'User: {user.email}, ID: {user.id}')
