from django.test import TestCase

from catalog.models import Product, ProductVariant
from orders.models import Order, OrderItem

from .models import ChannelAccount, ExternalListing, SyncJob
from .services import queue_external_fulfillment_for_order


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
