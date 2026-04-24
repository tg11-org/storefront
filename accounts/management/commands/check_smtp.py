from __future__ import annotations

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Validate SMTP configuration and optionally send a test email.'

    def add_arguments(self, parser):
        parser.add_argument('--to', dest='to_email', help='Recipient email for a live send test.')

    def handle(self, *args, **options):
        backend = settings.EMAIL_BACKEND
        host = settings.EMAIL_HOST
        port = settings.EMAIL_PORT
        tls = settings.EMAIL_USE_TLS
        ssl = settings.EMAIL_USE_SSL
        user = settings.EMAIL_HOST_USER or '(empty)'

        self.stdout.write(f'EMAIL_BACKEND={backend}')
        self.stdout.write(f'EMAIL_HOST={host}')
        self.stdout.write(f'EMAIL_PORT={port}')
        self.stdout.write(f'EMAIL_USE_TLS={tls}')
        self.stdout.write(f'EMAIL_USE_SSL={ssl}')
        self.stdout.write(f'EMAIL_HOST_USER={user}')

        if '://' in (host or ''):
            raise CommandError('EMAIL_HOST must be a hostname only (for example: mail.tg11.org), not a URL.')

        if tls and ssl:
            raise CommandError('EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be true.')

        connection = get_connection(fail_silently=False)
        try:
            connection.open()
            self.stdout.write(self.style.SUCCESS('SMTP connection opened successfully.'))
        except Exception as exc:  # pragma: no cover
            raise CommandError(f'Failed to open SMTP connection: {exc}') from exc
        finally:
            try:
                connection.close()
            except Exception:
                pass

        to_email = options.get('to_email')
        if not to_email:
            self.stdout.write(self.style.WARNING('No --to provided; connectivity check only.'))
            return

        message = EmailMessage(
            subject='[TG11 Shop] SMTP test',
            body='This is a test email sent by manage.py check_smtp.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
            connection=get_connection(fail_silently=False),
        )

        try:
            sent = message.send(fail_silently=False)
        except Exception as exc:  # pragma: no cover
            raise CommandError(f'SMTP send failed: {exc}') from exc

        if sent != 1:
            raise CommandError(f'SMTP send returned unexpected result: {sent}')

        self.stdout.write(self.style.SUCCESS(f'Test email sent to {to_email}.'))
