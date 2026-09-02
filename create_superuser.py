#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User

username = 'zakirfasi'
email = 'zakirfasi@example.com'
password = 'zakirfasi'

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f"Superuser '{username}' created successfully")
else:
    user = User.objects.get(username=username)
    user.set_password(password)
    user.save()
    print(f"Superuser '{username}' password updated successfully")
