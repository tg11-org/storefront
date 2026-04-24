from unittest.mock import Mock, patch

from django.test import override_settings
from django.test import TestCase

from catalog.models import Product, ProductVariant
from orders.models import Order, OrderItem

from .models import ChannelAccount, ExternalListing, SyncJob
from .popcustoms import PopCustomsConnector
from .services import process_pending_fulfillment_jobs, queue_external_fulfillment_for_order


class ExternalFulfillmentQueueTests(TestCase):
    def test_paid_external_order_creates_idempotent_submit_job(self):
        product = Product.objects.create(name='Pop Hoodie', slug='pop-hoodie', default_source=Product.Source.POPCUSTOMS)
        variant = ProductVariant.objects.create(product=product, title='XL', sku='HOOD-XL', price='55.00', stock_quantity=3, is_default=True)
        ChannelAccount.objects.create(provider=ChannelAccount.Provider.POPCUSTOMS, name='PopCustoms', account_identifier='pop-1')
        ExternalListing.objects.create(
            provider=ChannelAccount.Provider.POPCUSTOMS,
            channel_account=ChannelAccount.objects.get(account_identifier='pop-1'),
            product=product,
            variant=variant,
            external_listing_id='pop-listing-1',
            external_product_id='pop-product-1',
            external_variant_id='pop-variant-1',
        )
        order = Order.objects.create(
            email='buyer@example.com',
            status=Order.Status.PAID,
            source=Order.Source.POPCUSTOMS,
            shipping_address={'line1': '123 Market St'},
            grand_total='55.00',
        )
        OrderItem.objects.create(order=order, product=product, variant=variant, title=product.name, sku=variant.sku, quantity=1, unit_price='55.00', source=Order.Source.POPCUSTOMS)

        jobs = queue_external_fulfillment_for_order(order)
        queue_external_fulfillment_for_order(order)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(SyncJob.objects.count(), 1)
        job = SyncJob.objects.get()
        self.assertEqual(job.status, SyncJob.Status.PENDING)
        self.assertEqual(job.payload['items'][0]['external_listing_id'], 'pop-listing-1')
        order.refresh_from_db()
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.QUEUED)

    @override_settings(
        POPCUSTOMS_API_KEY='test-pop-key',
        POPCUSTOMS_ORDERS_ENDPOINT='https://i.popcustoms.test/stores/27713/webhooks/orders?platform=General',
        POPCUSTOMS_API_HEADER='X-API-Key',
        STRIPE_CURRENCY='usd',
    )
    @patch('connectors.popcustoms.requests.post')
    def test_popcustoms_connector_posts_order_to_configured_endpoint(self, mock_post):
        channel = ChannelAccount.objects.create(provider=ChannelAccount.Provider.POPCUSTOMS, name='PopCustoms', account_identifier='TG11')
        order = Order.objects.create(email='buyer@example.com', status=Order.Status.PAID, grand_total='24.00', shipping_address={'line1': '123 Market St'})
        mock_response = Mock()
        mock_response.json.return_value = {'id': 'pop-order-1'}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = PopCustomsConnector(channel).submit_order(order, [{'sku': 'MUG-001', 'title': 'Mug', 'quantity': 1, 'unit_price': '24.00'}])

        self.assertEqual(result['status'], 'submitted')
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs['headers']['X-API-Key'], 'test-pop-key')
        self.assertEqual(kwargs['json']['order']['number'], order.number)
        self.assertEqual(kwargs['json']['line_items'][0]['sku'], 'MUG-001')

    @override_settings(
        POPCUSTOMS_API_KEY='test-pop-key',
        POPCUSTOMS_ORDERS_ENDPOINT='https://i.popcustoms.test/stores/27713/webhooks/orders?platform=General',
        POPCUSTOMS_API_HEADER='X-API-Key',
    )
    @patch('connectors.popcustoms.requests.post')
    def test_process_pending_jobs_submits_popcustoms_order(self, mock_post):
        product = Product.objects.create(name='Pop Mug', slug='pop-mug', default_source=Product.Source.POPCUSTOMS)
        variant = ProductVariant.objects.create(product=product, title='Default', sku='MUG-001', price='24.00', stock_quantity=3, is_default=True)
        ChannelAccount.objects.create(provider=ChannelAccount.Provider.POPCUSTOMS, name='PopCustoms', account_identifier='TG11')
        order = Order.objects.create(email='buyer@example.com', status=Order.Status.PAID, source=Order.Source.POPCUSTOMS, grand_total='24.00')
        OrderItem.objects.create(order=order, product=product, variant=variant, title=product.name, sku=variant.sku, quantity=1, unit_price='24.00', source=Order.Source.POPCUSTOMS)
        queue_external_fulfillment_for_order(order)
        mock_response = Mock()
        mock_response.json.return_value = {'id': 'pop-order-1'}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        jobs = process_pending_fulfillment_jobs(provider=ChannelAccount.Provider.POPCUSTOMS)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].status, SyncJob.Status.SUCCEEDED)
        order.refresh_from_db()
        self.assertEqual(order.sync_state, Order.SyncState.SYNCED)
