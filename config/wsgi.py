"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Run migrations automatically on startup (for Render deployment)
if os.environ.get('DATABASE_URL'):
    try:
        import django
        django.setup()
        from django.core.management import call_command
        call_command('migrate', '--noinput', verbosity=0)
    except Exception:
        pass

application = get_wsgi_application()
