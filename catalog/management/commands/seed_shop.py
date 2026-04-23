from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import Address
from catalog.models import Product, ProductVariant
from connectors.models import ChannelAccount, ExternalListing


class Command(BaseCommand):
    help = 'Seed the TG11 shop with a starter catalog and admin user.'

    def handle(self, *args, **options):
        user_model = get_user_model()
        admin_user, created = user_model.objects.get_or_create(
            email='admin@shop.tg11.org',
            defaults={'is_staff': True, 'is_superuser': True, 'first_name': 'TG11', 'last_name': 'Admin'},
        )
        if created:
            admin_user.set_password('ChangeMe123!')
            admin_user.save()
            self.stdout.write(self.style.WARNING('Created admin@shop.tg11.org with password ChangeMe123!'))

        Address.objects.get_or_create(
            user=admin_user,
            address_type=Address.AddressType.SHIPPING,
            label='HQ',
            defaults={
                'full_name': 'TG11 Team',
                'line1': '11 Demo Street',
                'city': 'New York',
                'state': 'NY',
                'postal_code': '10001',
                'country': 'US',
                'is_default': True,
            },
        )

        native_product, _ = Product.objects.get_or_create(
            slug='tg11-studio-tee',
            defaults={
                'name': 'TG11 Studio Tee',
                'short_description': 'A direct-sale tee with a clean front print.',
                'description': 'Native product fulfilled internally.',
                'product_type': Product.ProductType.NATIVE,
                'default_source': Product.Source.INTERNAL,
                'is_featured': True,
            },
        )
        ProductVariant.objects.get_or_create(
            product=native_product,
            sku='TG11-TEE-BLK-M',
            defaults={'title': 'Black / Medium', 'price': Decimal('28.00'), 'stock_quantity': 50, 'is_default': True},
        )

        etsy_product, _ = Product.objects.get_or_create(
            slug='tg11-poster-drop',
            defaults={
                'name': 'TG11 Poster Drop',
                'short_description': 'A limited poster fulfilled through Etsy.',
                'description': 'External marketplace product linked through the Etsy connector scaffold.',
                'product_type': Product.ProductType.EXTERNAL,
                'default_source': Product.Source.ETSY,
                'is_featured': True,
            },
        )
        etsy_variant, _ = ProductVariant.objects.get_or_create(
            product=etsy_product,
            sku='TG11-POSTER-A2',
            defaults={'title': 'A2 Print', 'price': Decimal('35.00'), 'stock_quantity': 999, 'is_default': True},
        )

        channel, _ = ChannelAccount.objects.get_or_create(
            provider=ChannelAccount.Provider.ETSY,
            account_identifier='demo-etsy-shop',
            defaults={'name': 'Demo Etsy Shop', 'config': {'shop_id': 'demo-shop-id', 'api_key': 'replace-me'}},
        )
        ExternalListing.objects.get_or_create(
            provider=ChannelAccount.Provider.ETSY,
            channel_account=channel,
            product=etsy_product,
            variant=etsy_variant,
            external_listing_id='etsy-demo-listing-001',
            defaults={'listing_url': 'https://www.etsy.com/listing/demo'},
        )

        self.stdout.write(self.style.SUCCESS('Seed data loaded.'))
