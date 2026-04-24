from django.core.management.base import BaseCommand

from connectors.models import ChannelAccount
from connectors.services import process_pending_fulfillment_jobs


class Command(BaseCommand):
    help = 'Submit queued external fulfillment jobs to provider connectors.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--provider', choices=[choice[0] for choice in ChannelAccount.Provider.choices])

    def handle(self, *args, **options):
        jobs = process_pending_fulfillment_jobs(limit=options['limit'], provider=options.get('provider'))
        if not jobs:
            self.stdout.write('No pending fulfillment jobs.')
            return
        for job in jobs:
            self.stdout.write(f'{job.provider} {job.target_id}: {job.status}')
