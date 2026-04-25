from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from cart.models import Cart, CartItem
from catalog.models import Product, ProductVariant, StorePage
from orders.models import Order

from .models import Coupon, Promotion, PromotionScope, ShippingMethod, ShippingRateRule, ShippingWebhookEvent, ShippingZone
from .adapters import EasyPostAdapter, ShippoAdapter
from .services import calculate_cart_totals, quote_shipping_methods, scope_matches
from .tax import stripe_tax_calculation


class PricingScopeTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(name='Scope Tee', slug='scope-tee')
        self.variant = ProductVariant.objects.create(product=self.product, title='Default', sku='SCOPE-001', price='20.00', stock_quantity=10)
        self.cart = Cart.objects.create()
        self.item = CartItem.objects.create(cart=self.cart, product=self.product, variant=self.variant, quantity=1)
        self.promotion = Promotion.objects.create(name='Scoped sale', promotion_type=Promotion.PromotionType.PERCENT_OFF, value='10.00')

    def test_scope_matches_global_product_sku_and_page(self):
        page = StorePage.objects.create(title='Drop', slug='drop', is_published=True)
        page.products.add(self.product)

        self.assertTrue(scope_matches(PromotionScope.objects.create(promotion=self.promotion, scope_type=PromotionScope.ScopeType.GLOBAL), self.item))
        self.assertTrue(scope_matches(PromotionScope.objects.create(promotion=self.promotion, scope_type=PromotionScope.ScopeType.PRODUCT, product=self.product), self.item))
        self.assertTrue(scope_matches(PromotionScope.objects.create(promotion=self.promotion, scope_type=PromotionScope.ScopeType.SKUS, skus='NOPE,SCOPE-001'), self.item))
        self.assertTrue(scope_matches(PromotionScope.objects.create(promotion=self.promotion, scope_type=PromotionScope.ScopeType.PAGE, page=page), self.item))

    def test_coupon_validation_and_discount_total(self):
        user = get_user_model().objects.create_user(email='buyer@example.com', password='StrongPass123!')
        self.promotion.scopes.create(scope_type=PromotionScope.ScopeType.GLOBAL)
        coupon = Coupon.objects.create(code='save10', min_subtotal='10.00')
        coupon.promotions.add(self.promotion)

        totals = calculate_cart_totals(self.cart, customer=user, coupon_code='save10')

        self.assertEqual(totals.coupon, coupon)
        self.assertEqual(totals.discount_total, Decimal('2.00'))
        self.assertEqual(totals.grand_total, Decimal('18.00'))

    def test_rejected_coupon_is_reported(self):
        Coupon.objects.create(code='HIGH', min_subtotal='100.00')

        totals = calculate_cart_totals(self.cart, coupon_code='HIGH')

        self.assertEqual(totals.discount_total, Decimal('0.00'))
        self.assertEqual(totals.applied_rules[0].kind, 'coupon_rejected')


class ShippingQuoteTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(name='Ship Mug', slug='ship-mug')
        self.variant = ProductVariant.objects.create(
            product=self.product,
            title='Default',
            sku='SHIP-001',
            price='30.00',
            stock_quantity=10,
            weight_oz='12.00',
        )
        self.cart = Cart.objects.create()
        CartItem.objects.create(cart=self.cart, product=self.product, variant=self.variant, quantity=2)
        self.method = ShippingMethod.objects.create(name='Standard', carrier=ShippingMethod.Carrier.CUSTOM)
        self.domestic = ShippingZone.objects.create(name='US', countries='US')
        self.international = ShippingZone.objects.create(name='Worldwide', countries='*', unavailable_countries='US')
        ShippingRateRule.objects.create(zone=self.domestic, method=self.method, amount='6.95', fallback=True)
        ShippingRateRule.objects.create(zone=self.international, method=self.method, amount='24.95', fallback=True)

    def test_domestic_and_international_quotes_use_matching_zone(self):
        domestic_quotes = quote_shipping_methods({'country': 'US'}, self.cart)
        international_quotes = quote_shipping_methods({'country': 'CA'}, self.cart)

        self.assertEqual(domestic_quotes[0].amount, Decimal('6.95'))
        self.assertEqual(international_quotes[0].amount, Decimal('24.95'))

    def test_shipping_quote_is_included_in_totals(self):
        totals = calculate_cart_totals(self.cart, shipping_address={'country': 'US'})

        self.assertEqual(totals.shipping_total, Decimal('6.95'))
        self.assertEqual(totals.grand_total, Decimal('66.95'))


class LiveShippingAdapterTests(TestCase):
    @override_settings(EASYPOST_API_KEY='ez_test_key', EASYPOST_API_URL='https://api.easypost.test', STRIPE_CURRENCY='usd')
    @patch('pricing.adapters._post_json')
    def test_easypost_adapter_parses_rates(self, mock_post_json):
        mock_post_json.return_value = {
            'id': 'shp_123',
            'rates': [{'id': 'rate_123', 'carrier': 'USPS', 'service': 'Priority', 'rate': '7.42', 'currency': 'USD', 'delivery_days': 2}],
        }
        product = Product.objects.create(name='Live Tee', slug='live-tee')
        variant = ProductVariant.objects.create(product=product, title='Default', sku='LIVE-001', price='20.00', stock_quantity=2, weight_oz='8.00')
        cart = Cart.objects.create()
        item = CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=1)

        rates = EasyPostAdapter().quote({'country': 'US', 'postal_code': '10001'}, [item])

        self.assertEqual(rates[0].provider, 'easypost')
        self.assertEqual(rates[0].amount, Decimal('7.42'))
        self.assertEqual(rates[0].external_rate_id, 'rate_123')

    @override_settings(SHIPPO_API_TOKEN='shippo_test_key', SHIPPO_API_URL='https://api.goshippo.test', STRIPE_CURRENCY='usd')
    @patch('pricing.adapters._post_json')
    def test_shippo_adapter_parses_rates(self, mock_post_json):
        mock_post_json.return_value = {
            'object_id': 'shippo_shipment',
            'rates': [{'object_id': 'shippo_rate', 'provider': 'UPS', 'servicelevel': {'name': 'Ground'}, 'amount': '9.15', 'currency': 'USD', 'estimated_days': 4}],
        }
        product = Product.objects.create(name='Live Mug', slug='live-mug')
        variant = ProductVariant.objects.create(product=product, title='Default', sku='LIVE-002', price='20.00', stock_quantity=2, weight_oz='8.00')
        cart = Cart.objects.create()
        item = CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=1)

        rates = ShippoAdapter().quote({'country': 'US', 'postal_code': '10001'}, [item])

        self.assertEqual(rates[0].provider, 'shippo')
        self.assertEqual(rates[0].amount, Decimal('9.15'))
        self.assertEqual(rates[0].external_rate_id, 'shippo_rate')


class StripeTaxTests(TestCase):
    @override_settings(STRIPE_TAX_ENABLED=True, STRIPE_SECRET_KEY='sk_test_realish_value', STRIPE_CURRENCY='usd')
    @patch('pricing.tax.get_stripe_client')
    def test_stripe_tax_calculation_returns_tax_snapshot(self, mock_get_stripe_client):
        product = Product.objects.create(name='Tax Tee', slug='tax-tee')
        variant = ProductVariant.objects.create(product=product, title='Default', sku='TAX-001', price='20.00', stock_quantity=2)
        cart = Cart.objects.create()
        item = CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=1)
        client = Mock()
        client.tax.Calculation.create.return_value = SimpleNamespace(
            id='taxcalc_123',
            amount_total=2270,
            tax_amount_exclusive=270,
            tax_amount_inclusive=0,
            tax_breakdown=[],
        )
        mock_get_stripe_client.return_value = client

        tax_total, snapshot = stripe_tax_calculation([item], Decimal('20.00'), Decimal('5.00'), {'country': 'US', 'postal_code': '10001'})

        self.assertEqual(tax_total, Decimal('2.70'))
        self.assertEqual(snapshot['calculation_id'], 'taxcalc_123')


class ShippingWebhookTests(TestCase):
    def test_shippo_webhook_records_tracking_update(self):
        user = get_user_model().objects.create_user(email='buyer@example.com', password='StrongPass123!')
        order = Order.objects.create(user=user, email=user.email, status=Order.Status.PAID)
        payload = {
            'event': 'track_updated',
            'data': {
                'metadata': order.number,
                'tracking_number': '1Z999',
                'carrier': 'ups',
                'tracking_status': 'in_transit',
            },
        }

        response = self.client.post(reverse('pricing:shippo_webhook'), data=payload, content_type='application/json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(ShippingWebhookEvent.objects.get().processed)
        update = order.fulfillment_updates.get()
        self.assertEqual(update.tracking_number, '1Z999')
        self.assertEqual(update.status, Order.FulfillmentStatus.SHIPPED)

    @override_settings(EASYPOST_WEBHOOK_SECRET='secret')
    def test_easypost_webhook_rejects_bad_secret(self):
        response = self.client.post(reverse('pricing:easypost_webhook'), data={'id': 'evt_1'}, content_type='application/json')

        self.assertEqual(response.status_code, 403)
