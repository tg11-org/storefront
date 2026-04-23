from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Product(models.Model):
    class ProductType(models.TextChoices):
        NATIVE = 'native', 'Native'
        EXTERNAL = 'external', 'External'
        HYBRID = 'hybrid', 'Hybrid'

    class Source(models.TextChoices):
        INTERNAL = 'internal', 'Internal'
        ETSY = 'etsy', 'Etsy'
        POPCUSTOMS = 'popcustoms', 'PopCustoms'

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255)
    short_description = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    product_type = models.CharField(max_length=20, choices=ProductType.choices, default=ProductType.NATIVE)
    default_source = models.CharField(max_length=20, choices=Source.choices, default=Source.INTERNAL)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('catalog:product_detail', args=[self.slug])

    @property
    def primary_variant(self):
        return self.variants.filter(is_active=True).order_by('-is_default', 'price').first()

    @property
    def display_price(self) -> Decimal:
        variant = self.primary_variant
        return variant.price if variant else Decimal('0.00')

    @property
    def fulfillment_label(self) -> str:
        return self.get_default_source_display()


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    title = models.CharField(max_length=255, default='Default')
    sku = models.CharField(max_length=64, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product__name', '-is_default', 'title']
        constraints = [
            models.UniqueConstraint(fields=['product'], condition=models.Q(is_default=True), name='unique_default_variant_per_product'),
        ]

    def __str__(self) -> str:
        return f'{self.product.name} / {self.title}'


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='images', null=True, blank=True)
    image = models.ImageField(upload_to='products/', blank=True)
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self) -> str:
        return self.alt_text or f'Image for {self.product.name}'
