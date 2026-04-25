from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from catalog.models import Product, ProductVariant


class Cart(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='carts')
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    applied_coupon_code = models.CharField(max_length=48, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self) -> str:
        return f'Cart {self.pk}'

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items.all())

    @property
    def subtotal(self) -> Decimal:
        total = sum((item.line_total for item in self.items.select_related('variant')), Decimal('0.00'))
        return total.quantize(Decimal('0.01'))


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='cart_items')
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='cart_items')
    quantity = models.PositiveIntegerField(default=1)
    custom_request = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['cart', 'variant', 'custom_request'], name='unique_cart_variant_custom_request'),
        ]

    def __str__(self) -> str:
        return f'{self.quantity} x {self.variant}'

    @property
    def unit_price(self) -> Decimal:
        return self.variant.price

    @property
    def line_total(self) -> Decimal:
        return (self.variant.price * self.quantity).quantize(Decimal('0.01'))
