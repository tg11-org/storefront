from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Address
from catalog.models import Product, ProductVariant
from cart.models import Cart
from orders.models import Order
from pricing.services import ShippingQuote
from pricing.models import ShippingMethod, ShippingRateRule, ShippingZone
from pricing.tax import TaxProviderError


class CheckoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='buyer@example.com', password='StrongPass123!', first_name='Buyer')
        self.address = Address.objects.create(
            user=self.user,
            address_type=Address.AddressType.SHIPPING,
            label='Home',
            full_name='Buyer Person',
            line1='123 Market St',
            city='New York',
            state='NY',
            postal_code='10001',
            country='US',
            is_default=True,
        )
        self.product = Product.objects.create(name='TG11 Tee', slug='tg11-tee')
        self.variant = ProductVariant.objects.create(product=self.product, title='Default', sku='TEE-001', price=Decimal('30.00'), stock_quantity=10, is_default=True)
        self.client.login(email='buyer@example.com', password='StrongPass123!')
        cart = Cart.objects.create(user=self.user)
        cart.items.create(product=self.product, variant=self.variant, quantity=1, custom_request='Make it extra soft')
        zone = ShippingZone.objects.create(name='US', countries='US')
        method = ShippingMethod.objects.create(name='Standard')
        self.shipping_rule = ShippingRateRule.objects.create(zone=zone, method=method, amount='6.95', fallback=True)

    @patch('checkout.views.create_checkout_session')
    def test_checkout_creates_order_and_redirects_to_stripe(self, mock_create_checkout_session):
        mock_create_checkout_session.return_value.url = 'https://checkout.stripe.test/session'
        preview_response = self.client.post(reverse('checkout:start'), {'shipping_address': self.address.pk, 'same_as_shipping': True})
        self.assertEqual(preview_response.status_code, 200)
        response = self.client.post(reverse('checkout:start'), {'shipping_address': self.address.pk, 'same_as_shipping': True, 'shipping_rate_rule': f'rule:{self.shipping_rule.pk}', 'confirm_checkout': '1'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://checkout.stripe.test/session')
        order = Order.objects.get()
        self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)
        self.assertEqual(order.items.get().sku, 'TEE-001')
        self.assertEqual(order.items.get().custom_request, 'Make it extra soft')

    @override_settings(TAX_PROVIDER='stripe_tax', STRIPE_TAX_ENABLED=True, STRIPE_SECRET_KEY='sk_test_realish_value', STRIPE_CURRENCY='usd')
    @patch('pricing.tax.get_stripe_client')
    def test_checkout_preview_includes_tax_for_shipping_address(self, mock_get_stripe_client):
        client = mock_get_stripe_client.return_value
        client.tax.Calculation.create.return_value = SimpleNamespace(
            id='taxcalc_preview',
            amount_total=3905,
            tax_amount_exclusive=210,
            tax_amount_inclusive=0,
            tax_breakdown=[],
        )

        response = self.client.post(reverse('checkout:start'), {'shipping_address': self.address.pk, 'same_as_shipping': True})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '$2.10')
        _, kwargs = client.tax.Calculation.create.call_args
        self.assertEqual(kwargs['customer_details']['address']['state'], 'NY')

    @patch('checkout.views.create_checkout_session')
    @patch('checkout.views.quote_shipping_methods')
    def test_checkout_accepts_long_live_shipping_quote_id(self, mock_quote_shipping_methods, mock_create_checkout_session):
        quote = ShippingQuote(
            quote_id='easypost:rate_1234567890abcdefghijklmnopqrstuvwxyz',
            method_id=None,
            method_name='Priority',
            carrier='USPS',
            amount=Decimal('7.42'),
            estimated_min_days=2,
            estimated_max_days=2,
            rule_id=None,
            provider='easypost',
            external_rate_id='rate_1234567890abcdefghijklmnopqrstuvwxyz',
            external_shipment_id='shp_123',
        )
        mock_quote_shipping_methods.return_value = [quote]
        mock_create_checkout_session.return_value.url = 'https://checkout.stripe.test/session'

        preview_response = self.client.post(reverse('checkout:start'), {'shipping_address': self.address.pk, 'same_as_shipping': True})
        self.assertEqual(preview_response.status_code, 200)
        response = self.client.post(reverse('checkout:start'), {'shipping_address': self.address.pk, 'same_as_shipping': True, 'shipping_rate_rule': quote.quote_id, 'confirm_checkout': '1'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.get().shipping_rate_snapshot['quote_id'], quote.quote_id)

    @patch('checkout.views.quote_shipping_methods', return_value=[])
    def test_checkout_shows_error_when_no_shipping_quotes_exist(self, mock_quote_shipping_methods):
        response = self.client.post(reverse('checkout:start'), {'shipping_address': self.address.pk, 'same_as_shipping': True})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No shipping methods are available')

    def test_checkout_tax_failure_returns_form_error(self):
        self.client.post(reverse('checkout:start'), {'shipping_address': self.address.pk, 'same_as_shipping': True})

        with patch('checkout.views.calculate_cart_totals') as mock_calculate_cart_totals:
            mock_calculate_cart_totals.side_effect = TaxProviderError('Stripe Tax failed')
            response = self.client.post(reverse('checkout:start'), {'shipping_address': self.address.pk, 'same_as_shipping': True, 'shipping_rate_rule': f'rule:{self.shipping_rule.pk}', 'confirm_checkout': '1'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tax could not be calculated')

    @patch('checkout.views.create_checkout_session')
    def test_guest_checkout_creates_order_without_user(self, mock_create_checkout_session):
        self.client.logout()
        session = self.client.session
        if not session.session_key:
            session.save()
        guest_cart = Cart.objects.create(session_key=session.session_key)
        guest_cart.items.create(product=self.product, variant=self.variant, quantity=1)
        mock_create_checkout_session.return_value.url = 'https://checkout.stripe.test/session'

        preview_response = self.client.post(reverse('checkout:start'), {
            'email': 'guest@example.com',
            'full_name': 'Guest Buyer',
            'line1': '1 Main St',
            'city': 'Orlando',
            'postal_code': '32801',
            'country': 'US',
            'same_as_shipping': True,
        })
        self.assertEqual(preview_response.status_code, 200)

        response = self.client.post(reverse('checkout:start'), {
            'email': 'guest@example.com',
            'full_name': 'Guest Buyer',
            'line1': '1 Main St',
            'city': 'Orlando',
            'postal_code': '32801',
            'country': 'US',
            'same_as_shipping': True,
            'shipping_rate_rule': f'rule:{self.shipping_rule.pk}',
            'confirm_checkout': '1',
        })

        self.assertEqual(response.status_code, 302)
        order = Order.objects.latest('pk')
        self.assertIsNone(order.user)
        self.assertEqual(order.email, 'guest@example.com')

    @patch('checkout.views.finalize_order_from_checkout_session')
    def test_success_page_handles_finalize_failure(self, mock_finalize_order):
        order = Order.objects.create(user=self.user, email=self.user.email)
        mock_finalize_order.side_effect = RuntimeError('fulfillment side effect failed')

        response = self.client.get(reverse('checkout:success'), {'order': order.number, 'session_id': 'cs_test_123'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, order.number)

    @patch('checkout.views.finalize_order_from_checkout_session')
    def test_success_page_refreshes_order_after_finalize_failure(self, mock_finalize_order):
        order = Order.objects.create(user=self.user, email=self.user.email, status=Order.Status.PENDING_PAYMENT)

        def mark_paid_then_fail(session_id, **kwargs):
            Order.objects.filter(pk=order.pk).update(status=Order.Status.PAID)
            raise RuntimeError('later processing failed')

        mock_finalize_order.side_effect = mark_paid_then_fail

        response = self.client.get(reverse('checkout:success'), {'order': order.number, 'session_id': 'cs_test_123'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Paid')
