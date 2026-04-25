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
    allow_custom_requests = models.BooleanField(default=False)
    custom_request_label = models.CharField(max_length=120, blank=True, default='Custom request')
    custom_request_help_text = models.CharField(max_length=255, blank=True)
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
    max_order_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Optional per-order cap for fairness. Leave blank for no cap beyond stock.',
    )
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

    @property
    def effective_max_order_quantity(self) -> int:
        if self.max_order_quantity is None:
            return self.stock_quantity
        return min(self.stock_quantity, self.max_order_quantity)


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='images', null=True, blank=True)
    image = models.ImageField(upload_to='products/')
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self) -> str:
        return self.alt_text or f'Image for {self.product.name}'

    def clean(self):
        """Ensure max 5 images per product."""
        if self.pk is None:  # Only check for new images
            existing_count = ProductImage.objects.filter(product=self.product).count()
            if existing_count >= 5:
                from django.core.exceptions import ValidationError
                raise ValidationError('Maximum 5 images per product.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ProductVideo(models.Model):
    """Single video per product for showcase/demos."""
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='video')
    video = models.FileField(
        upload_to='products/videos/',
        help_text='Supported formats: MP4, WebM, Ogg (max 100MB)'
    )
    thumbnail = models.ImageField(upload_to='products/video_thumbnails/', blank=True, null=True)
    title = models.CharField(max_length=255, default='Product video')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f'Video: {self.product.name}'


class StorePage(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255)
    summary = models.CharField(max_length=255, blank=True)
    hero_image = models.ImageField(upload_to='pages/heroes/', blank=True)
    body = models.TextField(blank=True)
    products = models.ManyToManyField(Product, blank=True, related_name='store_pages')
    is_published = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'title']

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('catalog:page_detail', args=[self.slug])
