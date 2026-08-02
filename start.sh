#!/bin/bash
set -e

echo "Starting application..."
echo "Environment check:"
echo "DATABASE_URL is set: $(if [ -n "$DATABASE_URL" ]; then echo "YES"; else echo "NO"; fi)"
echo "Running database migrations..."
python manage.py migrate --noinput || echo "Migration failed, continuing anyway..."
echo "Starting gunicorn server..."
exec gunicorn config.wsgi --log-file -
