"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.management import call_command
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

# Apply migrations on startup (for Render deployment)
if os.environ.get('DATABASE_URL'):
    call_command('migrate', '--noinput')

# Create or reset the superuser named by the environment, for deployments
# without shell access
_superuser = os.environ.get('DJANGO_SUPERUSER_USERNAME')
_superuser_password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
if _superuser and _superuser_password:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=_superuser,
        defaults={'email': os.environ.get('DJANGO_SUPERUSER_EMAIL', '')},
    )
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.set_password(_superuser_password)
    user.save()
    print(f"=== SUPERUSER BOOTSTRAP: {'created' if created else 'password reset for'} '{_superuser}' ===")
else:
    print("=== SUPERUSER BOOTSTRAP: skipped, DJANGO_SUPERUSER_USERNAME/PASSWORD not both set ===")
