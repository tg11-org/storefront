from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from connectors.models import ChannelAccount, ExternalListing
from connectors.services import import_channel_listings, push_external_inventory, sync_external_listing


class Command(BaseCommand):
    help = 'Import listings or push listing/inventory data for a vendor channel.'

    def add_arguments(self, parser):
        parser.add_argument('--provider', choices=[choice[0] for choice in ChannelAccount.Provider.choices])
        parser.add_argument('--account', help='Channel account identifier. Defaults to the first active account for the provider.')
        parser.add_argument('--import-listings', action='store_true', help='Pull remote listings into local products and external listing links.')
        parser.add_argument('--push-listings', action='store_true', help='Create or update remote listings from local ExternalListing rows.')
        parser.add_argument('--push-inventory', action='store_true', help='Push current linked variant stock quantities.')
        parser.add_argument('--listing-id', help='Limit push operations to one local ExternalListing id.')
        parser.add_argument('--limit', type=int, default=50)

    def handle(self, *args, **options):
        if not any([options['import_listings'], options['push_listings'], options['push_inventory']]):
            raise CommandError('Choose at least one action: --import-listings, --push-listings, or --push-inventory.')

        channel = self._channel(options)
        count = 0

        if options['import_listings']:
            listings = import_channel_listings(channel, limit=options['limit'])
            count += len(listings)
            self.stdout.write(self.style.SUCCESS(f'Imported {len(listings)} {channel.get_provider_display()} listing(s).'))

        queryset = ExternalListing.objects.filter(channel_account=channel).select_related('channel_account', 'product', 'variant')
        if options['listing_id']:
            queryset = queryset.filter(pk=options['listing_id'])
        queryset = queryset.order_by('pk')[: options['limit']]

        if options['push_listings']:
            pushed = 0
            for listing in queryset:
                sync_external_listing(listing, push_inventory=False)
                pushed += 1
            count += pushed
            self.stdout.write(self.style.SUCCESS(f'Pushed {pushed} listing(s) to {channel.get_provider_display()}.'))

        if options['push_inventory']:
            pushed = 0
            for listing in queryset:
                push_external_inventory(listing)
                pushed += 1
            count += pushed
            self.stdout.write(self.style.SUCCESS(f'Pushed inventory for {pushed} listing(s) to {channel.get_provider_display()}.'))

        if count == 0:
            self.stdout.write(self.style.WARNING('No records matched the requested sync.'))

    def _channel(self, options) -> ChannelAccount:
        queryset = ChannelAccount.objects.filter(is_active=True, sync_enabled=True)
        if options['provider']:
            queryset = queryset.filter(provider=options['provider'])
        if options['account']:
            queryset = queryset.filter(account_identifier=options['account'])
        channel = queryset.order_by('pk').first()
        if not channel:
            raise CommandError('No active sync-enabled channel account matched those filters.')
        return channel
