from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models


class Promotion(models.Model):
    class PromotionType(models.TextChoices):
        PERCENT_OFF = 'percent_off', 'Percent off'
        FIXED_OFF = 'fixed_off', 'Fixed off'
        SALE_PRICE = 'sale_price', 'Sale price override'
        FREE_SHIPPING = 'free_shipping', 'Free shipping'

    class Source(models.TextChoices):
        MANUAL = 'manual', 'Manual'
        POPCUSTOMS = 'popcustoms', 'PopCustoms'

    name = models.CharField(max_length=160)
    promotion_type = models.CharField(max_length=24, choices=PromotionType.choices)
    value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    priority = models.IntegerField(default=100)
    combinable = models.BooleanField(default=False)
    min_subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    usage_count = models.PositiveIntegerField(default=0)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='promotions_created')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='promotions_updated')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', 'name']

    def __str__(self) -> str:
        return self.name


class PromotionScope(models.Model):
    class ScopeType(models.TextChoices):
        PRODUCT = 'product', 'Single product'
        PRODUCTS = 'products', 'Product list'
        SKU = 'sku', 'Single SKU'
        SKUS = 'skus', 'SKU list'
        PAGE = 'page', 'Single page'
        PAGES = 'pages', 'Page list'
        GLOBAL = 'global', 'Global'

    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE, related_name='scopes')
    scope_type = models.CharField(max_length=20, choices=ScopeType.choices, default=ScopeType.GLOBAL)
    product = models.ForeignKey('catalog.Product', on_delete=models.CASCADE, null=True, blank=True, related_name='promotion_scopes')
    products = models.ManyToManyField('catalog.Product', blank=True, related_name='promotion_list_scopes')
    variant = models.ForeignKey('catalog.ProductVariant', on_delete=models.CASCADE, null=True, blank=True, related_name='promotion_scopes')
    skus = models.TextField(blank=True, help_text='Comma-separated SKU list.')
    page = models.ForeignKey('catalog.StorePage', on_delete=models.CASCADE, null=True, blank=True, related_name='promotion_scopes')
    pages = models.ManyToManyField('catalog.StorePage', blank=True, related_name='promotion_list_scopes')

    def __str__(self) -> str:
        return f'{self.promotion} scope'


class Coupon(models.Model):
    code = models.CharField(max_length=48, unique=True)
    active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    max_total_uses = models.PositiveIntegerField(null=True, blank=True)
    max_uses_per_customer = models.PositiveIntegerField(null=True, blank=True)
    first_order_only = models.BooleanField(default=False)
    min_subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    combinable = models.BooleanField(default=False)
    promotions = models.ManyToManyField(Promotion, blank=True, related_name='coupons')
    usage_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='coupons_created')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='coupons_updated')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']

    def __str__(self) -> str:
        return self.code

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class CouponRedemption(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='redemptions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='coupon_redemptions')
    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, null=True, blank=True, related_name='coupon_redemptions')
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ShippingZone(models.Model):
    name = models.CharField(max_length=120)
    countries = models.TextField(default='US', help_text='Comma-separated ISO country codes. Use * for worldwide.')
    regions = models.TextField(blank=True, help_text='Optional comma-separated state/region codes.')
    unavailable_countries = models.TextField(blank=True, help_text='Comma-separated country codes blocked for this zone.')
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class ShippingMethod(models.Model):
    class Carrier(models.TextChoices):
        UPS = 'ups', 'UPS'
        USPS = 'usps', 'USPS'
        FEDEX = 'fedex', 'FedEx'
        DHL = 'dhl', 'DHL'
        CUSTOM = 'custom', 'Custom'

    name = models.CharField(max_length=120)
    carrier = models.CharField(max_length=20, choices=Carrier.choices, default=Carrier.CUSTOM)
    active = models.BooleanField(default=True)
    estimated_min_days = models.PositiveIntegerField(default=3)
    estimated_max_days = models.PositiveIntegerField(default=7)

    class Meta:
        ordering = ['carrier', 'name']

    def __str__(self) -> str:
        return self.name


class ShippingRateRule(models.Model):
    class RateType(models.TextChoices):
        FLAT = 'flat', 'Flat'
        WEIGHT_TIER = 'weight_tier', 'Weight tier'
        PRICE_TIER = 'price_tier', 'Price tier'
        FREE_SHIPPING = 'free_shipping', 'Free shipping override'

    zone = models.ForeignKey(ShippingZone, on_delete=models.CASCADE, related_name='rate_rules')
    method = models.ForeignKey(ShippingMethod, on_delete=models.CASCADE, related_name='rate_rules')
    rate_type = models.CharField(max_length=20, choices=RateType.choices, default=RateType.FLAT)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    min_weight_oz = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    max_weight_oz = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    max_subtotal = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    active = models.BooleanField(default=True)
    fallback = models.BooleanField(default=False)
    priority = models.IntegerField(default=100)

    class Meta:
        ordering = ['priority', 'amount']

    def __str__(self) -> str:
        return f'{self.method} / {self.zone}'


class ShippingWebhookEvent(models.Model):
    provider = models.CharField(max_length=32)
    event_id = models.CharField(max_length=255, blank=True, db_index=True)
    event_type = models.CharField(max_length=120, blank=True)
    order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='shipping_webhook_events')
    payload = models.JSONField(default=dict, blank=True)
    processed = models.BooleanField(default=False)
    message = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['provider', 'event_id']),
        ]

    def __str__(self) -> str:
        return f'{self.provider} {self.event_type or self.event_id or self.pk}'
