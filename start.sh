#!/bin/bash
set -e

echo "=== Starting Application ==="
echo "Running database migrations..."
python manage.py migrate --noinput
echo "Migrations completed successfully"
echo "Starting gunicorn server..."
exec gunicorn config.wsgi --log-file -
