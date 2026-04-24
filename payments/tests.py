from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Product, ProductVariant
from connectors.models import ChannelAccount, SyncJob
from orders.models import Order, OrderItem

from .services import StripeConfigurationError, finalize_order_from_checkout_session, get_stripe_client, is_configured_stripe_value


class StripeConfigurationTests(TestCase):
    def test_placeholder_values_are_not_configured(self):
        self.assertFalse(is_configured_stripe_value('sk_test_replace_me'))
        self.assertFalse(is_configured_stripe_value('whsec_replace_me'))
        self.assertFalse(is_configured_stripe_value(''))
        self.assertTrue(is_configured_stripe_value('sk_test_realish_value'))

    @override_settings(STRIPE_SECRET_KEY='sk_test_replace_me')
    def test_get_stripe_client_rejects_placeholder_secret(self):
        with self.assertRaises(StripeConfigurationError):
            get_stripe_client()

    @override_settings(STRIPE_SECRET_KEY='sk_test_replace_me', STRIPE_WEBHOOK_SECRET='whsec_replace_me')
    def test_webhook_returns_unavailable_when_stripe_uses_placeholders(self):
        response = self.client.post(reverse('payments:stripe_webhook'), data=b'{}', content_type='application/json')
        self.assertEqual(response.status_code, 503)


class StripeCheckoutFinalizationTests(TestCase):
    @override_settings(STRIPE_SECRET_KEY='sk_test_realish_value')
    @patch('payments.services.get_stripe_client')
    def test_paid_external_checkout_queues_fulfillment_job(self, mock_get_stripe_client):
        product = Product.objects.create(name='Pop Tee', slug='pop-tee', default_source=Product.Source.POPCUSTOMS)
        variant = ProductVariant.objects.create(product=product, title='Default', sku='POP-TEE', price='25.00', stock_quantity=5, is_default=True)
        ChannelAccount.objects.create(provider=ChannelAccount.Provider.POPCUSTOMS, name='PopCustoms', account_identifier='pop-1')
        order = Order.objects.create(
            email='buyer@example.com',
            status=Order.Status.PENDING_PAYMENT,
            source=Order.Source.POPCUSTOMS,
            grand_total='25.00',
        )
        OrderItem.objects.create(order=order, product=product, variant=variant, title=product.name, sku=variant.sku, quantity=1, unit_price='25.00', source=Order.Source.POPCUSTOMS)
        session = SimpleNamespace(
            id='cs_test_123',
            metadata={'order_number': order.number},
            client_reference_id=order.number,
            payment_status='paid',
            payment_intent='pi_test_123',
        )
        mock_client = Mock()
        mock_client.checkout.Session.retrieve.return_value = session
        mock_get_stripe_client.return_value = mock_client

        finalized_order = finalize_order_from_checkout_session(session.id)

        self.assertEqual(finalized_order.status, Order.Status.PAID)
        self.assertEqual(SyncJob.objects.filter(action='submit_order', provider=ChannelAccount.Provider.POPCUSTOMS).count(), 1)
