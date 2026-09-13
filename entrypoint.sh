#!/bin/sh
set -eu

python - <<'PY'
import os
import time
import django
from django.db import connections
from django.db.utils import OperationalError

os.environ.setdefault('DJANGO_SETTINGS_MODULE', os.getenv('DJANGO_SETTINGS_MODULE', 'config.settings.prod'))
django.setup()

for attempt in range(1, 31):
    try:
        conn = connections['default']
        conn.cursor()
        print('Database connection established.')
        break
    except OperationalError as exc:
        print(f'Waiting for database (attempt {attempt}/30): {exc}')
        time.sleep(2)
else:
    raise SystemExit('Database never became available.')
PY

python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application --bind "${GUNICORN_BIND:-127.6.0.10:8000}" --workers "${GUNICORN_WORKERS:-3}" --timeout "${GUNICORN_TIMEOUT:-60}"
