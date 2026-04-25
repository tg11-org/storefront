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

    def test_add_to_cart_rejects_quantity_over_stock(self):
        response = self.client.post(reverse('cart:add', args=[self.product.slug]), {'variant_id': self.variant.pk, 'quantity': 6})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Cart.objects.get().items.count(), 0)

    def test_add_to_cart_handles_invalid_quantity_without_500(self):
        response = self.client.post(reverse('cart:add', args=[self.product.slug]), {'variant_id': self.variant.pk, 'quantity': 'nope'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Cart.objects.get().items.get().quantity, 1)

    def test_update_cart_rejects_quantity_over_stock(self):
        self.client.post(reverse('cart:add', args=[self.product.slug]), {'variant_id': self.variant.pk, 'quantity': 2})
        item = Cart.objects.get().items.get()

        response = self.client.post(reverse('cart:update_item', args=[item.pk]), {'quantity': 6})

        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    def test_custom_request_creates_distinct_cart_lines(self):
        self.product.allow_custom_requests = True
        self.product.custom_request_label = 'Dice request'
        self.product.save(update_fields=['allow_custom_requests', 'custom_request_label', 'updated_at'])

        self.client.post(reverse('cart:add', args=[self.product.slug]), {'variant_id': self.variant.pk, 'quantity': 1, 'custom_request': 'Blue shimmer'})
        self.client.post(reverse('cart:add', args=[self.product.slug]), {'variant_id': self.variant.pk, 'quantity': 1, 'custom_request': 'Red swirl'})

        cart = Cart.objects.get()
        self.assertEqual(cart.items.count(), 2)
        self.assertEqual(set(cart.items.values_list('custom_request', flat=True)), {'Blue shimmer', 'Red swirl'})

    def test_product_page_only_shows_custom_request_when_enabled(self):
        response = self.client.get(reverse('catalog:product_detail', args=[self.product.slug]))
        self.assertNotContains(response, 'name="custom_request"')

        self.product.allow_custom_requests = True
        self.product.custom_request_label = 'Dice request'
        self.product.save(update_fields=['allow_custom_requests', 'custom_request_label', 'updated_at'])

        response = self.client.get(reverse('catalog:product_detail', args=[self.product.slug]))
        self.assertContains(response, 'Dice request')
        self.assertContains(response, 'name="custom_request"')
