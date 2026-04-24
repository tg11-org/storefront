from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Product, ProductVariant, StorePage
from connectors.models import ChannelAccount, ExternalListing


class DashboardManagerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(email='admin@example.com', password='StrongPass123!')
        self.client.login(email='admin@example.com', password='StrongPass123!')

    def test_superuser_sees_dashboard_link_in_base_nav(self):
        response = self.client.get(reverse('catalog:home'))

        self.assertContains(response, reverse('dashboard:manage'))
        self.assertContains(response, 'Dashboard')

    def test_product_create_creates_product_and_default_variant(self):
        response = self.client.post(
            reverse('dashboard:product_create'),
            {
                'product-name': 'TG11 Poster',
                'product-slug': 'tg11-poster',
                'product-short_description': 'Wall print',
                'product-description': 'A TG11 print.',
                'product-product_type': Product.ProductType.NATIVE,
                'product-default_source': Product.Source.INTERNAL,
                'product-is_active': 'on',
                'product-is_featured': 'on',
                'variant-title': 'Default',
                'variant-sku': 'POSTER-001',
                'variant-price': '18.00',
                'variant-compare_at_price': '',
                'variant-stock_quantity': '20',
                'variant-is_active': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(slug='tg11-poster')
        self.assertTrue(product.is_featured)
        self.assertEqual(product.variants.get().sku, 'POSTER-001')
        self.assertTrue(product.variants.get().is_default)

    def test_page_create_links_products(self):
        product = Product.objects.create(name='Linked Tee', slug='linked-tee')

        response = self.client.post(
            reverse('dashboard:page_create'),
            {
                'title': 'Linked Drop',
                'slug': 'linked-drop',
                'summary': 'A small collection.',
                'body': 'Drop notes.',
                'products': [str(product.pk)],
                'is_published': 'on',
                'sort_order': '0',
            },
        )

        self.assertEqual(response.status_code, 302)
        page = StorePage.objects.get(slug='linked-drop')
        self.assertEqual(list(page.products.all()), [product])

    def test_channel_and_listing_create_flow(self):
        product = Product.objects.create(name='Pop Mug', slug='pop-mug', default_source=Product.Source.POPCUSTOMS)
        variant = ProductVariant.objects.create(product=product, title='Default', sku='MUG-001', price='14.00', stock_quantity=10, is_default=True)

        channel_response = self.client.post(
            reverse('dashboard:channel_create'),
            {
                'provider': ChannelAccount.Provider.POPCUSTOMS,
                'name': 'PopCustoms Main',
                'account_identifier': 'pop-main',
                'access_token': '',
                'refresh_token': '',
                'config_text': '{"sandbox": true}',
                'is_active': 'on',
                'sync_enabled': 'on',
            },
        )

        self.assertEqual(channel_response.status_code, 302)
        channel = ChannelAccount.objects.get(account_identifier='pop-main')
        self.assertEqual(channel.config, {'sandbox': True})

        listing_response = self.client.post(
            reverse('dashboard:listing_create'),
            {
                'channel_account': str(channel.pk),
                'product': str(product.pk),
                'variant': str(variant.pk),
                'external_listing_id': 'pop-listing-100',
                'external_product_id': 'pop-product-100',
                'external_variant_id': 'pop-variant-100',
                'listing_url': '',
            },
        )

        self.assertEqual(listing_response.status_code, 302)
        listing = ExternalListing.objects.get(external_listing_id='pop-listing-100')
        self.assertEqual(listing.provider, ChannelAccount.Provider.POPCUSTOMS)
