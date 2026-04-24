from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Address
from catalog.models import Product, ProductVariant
from cart.models import Cart
from orders.models import Order


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

    @patch('checkout.views.create_checkout_session')
    def test_checkout_creates_order_and_redirects_to_stripe(self, mock_create_checkout_session):
        mock_create_checkout_session.return_value.url = 'https://checkout.stripe.test/session'
        response = self.client.post(reverse('checkout:start'), {'shipping_address': self.address.pk, 'same_as_shipping': True})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://checkout.stripe.test/session')
        order = Order.objects.get()
        self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)
        self.assertEqual(order.items.get().sku, 'TEE-001')
        self.assertEqual(order.items.get().custom_request, 'Make it extra soft')

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
