from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Product, ProductVariant, StorePage


class StorePageTests(TestCase):
    def test_published_page_displays_linked_products(self):
        product = Product.objects.create(name='TG11 Print', slug='tg11-print', is_active=True)
        ProductVariant.objects.create(product=product, title='Default', sku='PRINT-001', price='12.00', stock_quantity=5, is_default=True)
        page = StorePage.objects.create(title='Print Drop', slug='print-drop', is_published=True)
        page.products.add(product)

        response = self.client.get(reverse('catalog:page_detail', args=[page.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Print Drop')
        self.assertContains(response, 'TG11 Print')

    def test_superuser_can_open_storefront_manager(self):
        user = get_user_model().objects.create_superuser(email='admin@example.com', password='StrongPass123!')
        self.client.login(email='admin@example.com', password='StrongPass123!')

        response = self.client.get(reverse('dashboard:manage'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Manage storefront')
        self.assertContains(response, 'Add product')


class ExternalPricingTests(TestCase):
    @override_settings(
        POPCUSTOMS_PRICING_OVERHEAD='8.95',
        EXTERNAL_RETAIL_MARKUP_PERCENT='35',
        EXTERNAL_RETAIL_ROUND_TO='1.00',
        EXTERNAL_RETAIL_PRICE_ENDING='0.99',
        AUTO_ENFORCE_EXTERNAL_RETAIL_FLOOR=True,
    )
    def test_external_variant_price_is_raised_to_supplier_floor(self):
        product = Product.objects.create(
            name='Pop Hoodie',
            slug='pop-hoodie',
            product_type=Product.ProductType.EXTERNAL,
            default_source=Product.Source.POPCUSTOMS,
        )

        variant = ProductVariant.objects.create(
            product=product,
            title='M',
            sku='POP-HOODIE-M',
            price=Decimal('17.49'),
            supplier_price=Decimal('17.49'),
            stock_quantity=0,
        )

        self.assertEqual(variant.price, Decimal('35.99'))
        self.assertEqual(variant.recommended_retail_price, Decimal('35.99'))
