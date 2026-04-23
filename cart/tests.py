from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from catalog.models import Product, ProductVariant
from cart.models import Cart


class CartTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(name='Sticker Pack', slug='sticker-pack')
        self.variant = ProductVariant.objects.create(product=self.product, title='Default', sku='STICKER-001', price=Decimal('12.00'), stock_quantity=5, is_default=True)

    def test_add_to_cart_creates_item(self):
        response = self.client.post(reverse('cart:add', args=[self.product.slug]), {'variant_id': self.variant.pk, 'quantity': 2})
        self.assertEqual(response.status_code, 302)
        cart = Cart.objects.get()
        self.assertEqual(cart.items.get().quantity, 2)
        self.assertEqual(cart.subtotal, Decimal('24.00'))
