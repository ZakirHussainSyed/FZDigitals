#!/bin/bash
set -e

echo "Starting application..."
echo "Running database migrations..."
python manage.py migrate --noinput || echo "Migration failed, continuing anyway..."
echo "Starting gunicorn server..."
exec gunicorn config.wsgi --log-file -
