#!/usr/bin/env python3
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp

print("Starting OAuth configuration...", file=sys.stderr)

try:
    # Configure Sites
    site, created = Site.objects.get_or_create(
        id=1,
        defaults={'domain': '127.0.0.1:8000', 'name': 'FZDigitals Local'}
    )
    if not created:
        site.domain = '127.0.0.1:8000'
        site.name = 'FZDigitals Local'
        site.save()
    print(f"Site configured: {site.domain} - {site.name}", file=sys.stderr)

    # Note: You need to add your Google OAuth credentials below
    # Replace with your actual Client ID and Secret from Google Cloud Console
    GOOGLE_CLIENT_ID = "1080919588132-anbs9i6hg877r7uk4vghi8c25cmttnsr.apps.googleusercontent.com"
    GOOGLE_CLIENT_SECRET = "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"

    # Create Social App
    app, created = SocialApp.objects.get_or_create(
        provider='google',
        defaults={'name': 'FZDigitals Google', 'client_id': GOOGLE_CLIENT_ID, 'secret': GOOGLE_CLIENT_SECRET}
    )
    if not created:
        app.name = 'FZDigitals Google'
        app.client_id = GOOGLE_CLIENT_ID
        app.secret = GOOGLE_CLIENT_SECRET
        app.save()

    # Add site to social app
    app.sites.add(site)
    print(f"Social App configured: {app.name}", file=sys.stderr)
    print("Configuration completed successfully!", file=sys.stderr)
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
