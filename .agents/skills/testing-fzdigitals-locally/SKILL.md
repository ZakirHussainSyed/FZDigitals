---
name: testing-fzdigitals-locally
description: How to run the FZDigitals Django app locally (DEBUG=False / production-like, static files, test user, login flow) for end-to-end browser testing.
---

# Running FZDigitals locally for testing

## Environment
- Create a venv and install deps: `python3 -m venv /tmp/v && /tmp/v/bin/pip install -r requirements.txt`.
- No `DATABASE_URL` ⇒ sqlite fallback (`config/settings.py`), so no Postgres is needed locally.
- `DEBUG` is parsed as `os.environ.get('DEBUG','True') == 'True'`, i.e. any value other than the exact string `True` means debug off.

## Production-like run (required for static-file testing)
```bash
DEBUG=False SECRET_KEY=test /tmp/v/bin/python manage.py migrate --noinput
DEBUG=False SECRET_KEY=test /tmp/v/bin/python manage.py collectstatic --noinput   # populates ./staticfiles (gitignored)
DEBUG=False SECRET_KEY=test HTTPS_ONLY=False ALLOWED_HOSTS=localhost,127.0.0.1 \
  /tmp/v/bin/python manage.py runserver 127.0.0.1:8000 --noreload
```
Gotchas:
- `HTTPS_ONLY=False` is required locally: otherwise `DEBUG=False` turns on `SECURE_SSL_REDIRECT` and secure-only cookies, so plain-http localhost redirects to https and login fails.
- `SECRET_KEY` is mandatory when `DEBUG=False` (settings raise `ImproperlyConfigured` without it).
- With `DEBUG=False`, WhiteNoise indexes `STATIC_ROOT` **once at process start**. After running (or removing) `collectstatic`, you MUST restart the server or `/static/...` results will not change.
- Templates hardcode `/static/logo.png` (not `{% static %}`), so the non-hashed copy in `staticfiles/` is what gets served even with `CompressedManifestStaticFilesStorage`.
- Browsers aggressively cache the logo; use ctrl+shift+R when checking whether a static asset now 404s/renders.
- Start the server detached with `setsid nohup ... &`; plain background jobs in a short-lived shell tool call can be killed when the call times out.

## Test user + login flow
```bash
/tmp/v/bin/python -c "
import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); django.setup()
from django.contrib.auth.models import User
User.objects.create_user('testuser','t@e.com','TestPass123!')"
```
- Login page: `/login/` (`slideshow.views.django_login`, template `slideshow/templates/slideshow/login.html`).
- Successful login redirects to `/<user.id>/` (the slideshow dashboard). Already-authenticated visits to `/login/` also redirect there — log out via the "Logout" link (`/accounts/logout/` → "Yes, Sign Out") before re-testing the login page.

## Devin Secrets Needed
None — local sqlite + a throwaway SECRET_KEY are sufficient. AWS/S3 vars are optional; without `AWS_STORAGE_BUCKET_NAME` media uses the local filesystem.
