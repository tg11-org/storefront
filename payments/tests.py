from types import SimpleNamespace
from unittest.mock import Mock, patch

import stripe
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Product, ProductVariant
from connectors.models import ChannelAccount, SyncJob
from orders.models import Order, OrderItem

from .services import StripeConfigurationError, create_setup_session, finalize_order_from_checkout_session, get_stripe_client, is_configured_stripe_value


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

    @patch('payments.views.create_setup_session')
    def test_add_payment_method_handles_stripe_errors(self, mock_create_setup_session):
        user = get_user_model().objects.create_user(email='buyer@example.com', password='StrongPass123!')
        self.client.login(email='buyer@example.com', password='StrongPass123!')
        mock_create_setup_session.side_effect = stripe.error.PermissionError('Missing permission')

        response = self.client.get(reverse('payments:add_method'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:dashboard'))

    @override_settings(STRIPE_SECRET_KEY='sk_test_realish_value', STRIPE_CURRENCY='usd')
    @patch('payments.services.get_stripe_client')
    def test_create_setup_session_sends_currency(self, mock_get_stripe_client):
        user = get_user_model().objects.create_user(email='buyer@example.com', password='StrongPass123!')
        mock_client = Mock()
        mock_client.Customer.create.return_value = SimpleNamespace(id='cus_test_123')
        mock_client.checkout.Session.create.return_value = SimpleNamespace(url='https://checkout.stripe.test/setup')
        mock_get_stripe_client.return_value = mock_client

        create_setup_session(user, 'https://shop.tg11.org/setup/success', 'https://shop.tg11.org/account/')

        _, kwargs = mock_client.checkout.Session.create.call_args
        self.assertEqual(kwargs['mode'], 'setup')
        self.assertEqual(kwargs['currency'], 'usd')


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

    @override_settings(
        STRIPE_SECRET_KEY='sk_test_realish_value',
        FULFILLMENT_EMAIL_RECIPIENTS=['orders@example.com'],
        DEFAULT_FROM_EMAIL='TG11 Shop <no-reply@example.com>',
    )
    @patch('payments.services.get_stripe_client')
    def test_paid_internal_checkout_decrements_inventory_and_sends_email_once(self, mock_get_stripe_client):
        product = Product.objects.create(name='TG11 Candle', slug='tg11-candle', default_source=Product.Source.INTERNAL)
        variant = ProductVariant.objects.create(product=product, title='Vanilla', sku='CANDLE-001', price='18.00', stock_quantity=4, is_default=True)
        order = Order.objects.create(
            email='buyer@example.com',
            status=Order.Status.PENDING_PAYMENT,
            source=Order.Source.INTERNAL,
            grand_total='36.00',
            shipping_address={
                'full_name': 'Buyer Person',
                'line1': '123 Market St',
                'city': 'New York',
                'state': 'NY',
                'postal_code': '10001',
                'country': 'US',
            },
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            variant=variant,
            title=product.name,
            sku=variant.sku,
            quantity=2,
            unit_price='18.00',
            source=Order.Source.INTERNAL,
            custom_request='Please include gold flakes.',
        )
        session = SimpleNamespace(
            id='cs_test_456',
            metadata={'order_number': order.number},
            client_reference_id=order.number,
            payment_status='paid',
            payment_intent='pi_test_456',
        )
        mock_client = Mock()
        mock_client.checkout.Session.retrieve.return_value = session
        mock_get_stripe_client.return_value = mock_client

        finalize_order_from_checkout_session(session.id)
        finalize_order_from_checkout_session(session.id)

        variant.refresh_from_db()
        self.assertEqual(variant.stock_quantity, 2)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('TG11 Candle', mail.outbox[0].body)
        self.assertIn('Please include gold flakes.', mail.outbox[0].body)
        self.assertIn('123 Market St', mail.outbox[0].body)

    @override_settings(STRIPE_SECRET_KEY='sk_test_realish_value')
    @patch('payments.services.decrement_internal_inventory')
    @patch('payments.services.get_stripe_client')
    def test_finalize_marks_order_paid_even_if_fulfillment_side_effect_fails(self, mock_get_stripe_client, mock_decrement_inventory):
        order = Order.objects.create(
            email='buyer@example.com',
            status=Order.Status.PENDING_PAYMENT,
            source=Order.Source.INTERNAL,
            grand_total='18.00',
        )
        mock_decrement_inventory.side_effect = RuntimeError('inventory failed')
        session = SimpleNamespace(
            id='cs_test_789',
            metadata={'order_number': order.number},
            client_reference_id=order.number,
            payment_status='paid',
            payment_intent='pi_test_789',
        )
        mock_client = Mock()
        mock_client.checkout.Session.retrieve.return_value = session
        mock_get_stripe_client.return_value = mock_client

        finalized_order = finalize_order_from_checkout_session(session.id)

        self.assertEqual(finalized_order.status, Order.Status.PAID)
        self.assertEqual(finalized_order.stripe_payment_intent_id, 'pi_test_789')

    @override_settings(STRIPE_SECRET_KEY='sk_test_realish_value')
    @patch('payments.services.get_stripe_client')
    def test_finalize_can_use_explicit_order_number_without_session_metadata(self, mock_get_stripe_client):
        order = Order.objects.create(
            email='buyer@example.com',
            status=Order.Status.PENDING_PAYMENT,
            source=Order.Source.INTERNAL,
            grand_total='18.00',
        )
        session = SimpleNamespace(
            id='cs_test_no_metadata',
            metadata=None,
            client_reference_id='',
            payment_status='paid',
            payment_intent='pi_test_no_metadata',
        )
        mock_client = Mock()
        mock_client.checkout.Session.retrieve.return_value = session
        mock_get_stripe_client.return_value = mock_client

        finalized_order = finalize_order_from_checkout_session(session.id, order_number=order.number)

        self.assertEqual(finalized_order.status, Order.Status.PAID)
        self.assertEqual(finalized_order.stripe_payment_intent_id, 'pi_test_no_metadata')
