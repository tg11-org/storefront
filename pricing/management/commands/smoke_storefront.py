from __future__ import annotations

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.test import Client


class Command(BaseCommand):
    help = 'Run lightweight per-store smoke checks for deployment validation.'

    def handle(self, *args, **options):
        call_command('check', '--deploy')
        client = Client(HTTP_HOST=settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost')
        for path in ['/', '/products/', '/cart/', '/health/']:
            response = client.get(path)
            if response.status_code >= 500:
                raise SystemExit(f'{path} returned {response.status_code}')
            self.stdout.write(f'{path}: {response.status_code}')
        self.stdout.write(self.style.SUCCESS('Storefront smoke checks passed.'))
