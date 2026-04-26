from __future__ import annotations

from decimal import Decimal, ROUND_UP

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


SIZE_ORDER_MAP = {
    'xxs': 0,
    'extra extra small': 0,
    'xs': 1,
    'xsmall': 1,
    'extra small': 1,
    's': 2,
    'small': 2,
    'm': 3,
    'medium': 3,
    'l': 4,
    'large': 4,
    'xl': 5,
    'xlarge': 5,
    'extra large': 5,
    'xxl': 6,
    '2xl': 6,
    '2xlarge': 6,
    'extra extra large': 6,
    'xxxl': 7,
    '3xl': 7,
    '3xlarge': 7,
    '4xl': 8,
    '4xlarge': 8,
    '5xl': 9,
    '5xlarge': 9,
    '6xl': 10,
    '6xlarge': 10,
    '7xl': 11,
    '7xlarge': 11,
    '8xl': 12,
    '8xlarge': 12,
}

DISPLAY_SIZE_LABELS = {
    'xxs': 'XXS',
    'xs': 'XS',
    'xsmall': 'XS',
    'small': 'Small',
    's': 'Small',
    'medium': 'Medium',
    'm': 'Medium',
    'large': 'Large',
    'l': 'Large',
    'xl': 'XL',
    'xlarge': 'XL',
    '2xl': '2XL',
    '2xlarge': '2XL',
    'xxl': '2XL',
    '3xl': '3XL',
    '3xlarge': '3XL',
    'xxxl': '3XL',
    '4xl': '4XL',
    '4xlarge': '4XL',
    '5xl': '5XL',
    '5xlarge': '5XL',
    '6xl': '6XL',
    '6xlarge': '6XL',
    '7xl': '7XL',
    '7xlarge': '7XL',
    '8xl': '8XL',
    '8xlarge': '8XL',
}


def normalize_size_key(value: str | None) -> str:
    if not value:
        return ''
    normalized = ''.join(character.lower() if character.isalnum() else ' ' for character in value)
    return ' '.join(normalized.split())


def display_size_label_for(value: str | None) -> str:
    key = normalize_size_key(value)
    compact = key.replace(' ', '')
    return DISPLAY_SIZE_LABELS.get(key) or DISPLAY_SIZE_LABELS.get(compact) or (value or '').strip()


def sort_order_for_size(value: str | None) -> int | None:
    key = normalize_size_key(value)
    compact = key.replace(' ', '')
    if compact in SIZE_ORDER_MAP:
        return SIZE_ORDER_MAP[compact]
    if key in SIZE_ORDER_MAP:
        return SIZE_ORDER_MAP[key]
    return None


def source_shipping_overhead(source: str) -> Decimal:
    source_key = (source or '').lower()
    if source_key == 'popcustoms':
        configured = getattr(settings, 'POPCUSTOMS_PRICING_OVERHEAD', '')
        if configured:
            return Decimal(str(configured))
        return Decimal(str(getattr(settings, 'POPCUSTOMS_FALLBACK_DOMESTIC_SHIPPING_AMOUNT', '0.00')))
    return Decimal('0.00')


def calculate_external_retail_price(source: str, supplier_cost: Decimal | str | None) -> Decimal | None:
    if supplier_cost in (None, ''):
        return None
    supplier_total = Decimal(str(supplier_cost))
    markup_percent = Decimal(str(getattr(settings, 'EXTERNAL_RETAIL_MARKUP_PERCENT', '35')))
    rounded_to = Decimal(str(getattr(settings, 'EXTERNAL_RETAIL_ROUND_TO', '1.00')))
    price_ending = Decimal(str(getattr(settings, 'EXTERNAL_RETAIL_PRICE_ENDING', '0.99')))
    raw_price = (supplier_total + source_shipping_overhead(source)) * (Decimal('1.00') + (markup_percent / Decimal('100')))
    if rounded_to <= 0:
        return raw_price.quantize(Decimal('0.01'))
    rounded_price = (raw_price / rounded_to).to_integral_value(rounding=ROUND_UP) * rounded_to
    if Decimal('0.00') <= price_ending < rounded_to:
        candidate = rounded_price - (rounded_to - price_ending)
        if candidate < raw_price:
            candidate += rounded_to
        rounded_price = candidate
    return rounded_price.quantize(Decimal('0.01'))


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
        return self.variants.filter(is_active=True).order_by('-is_default', 'sort_order', 'title', 'price').first()

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
    size_label = models.CharField(max_length=64, blank=True)
    sku = models.CharField(max_length=64, unique=True)
    sort_order = models.PositiveIntegerField(default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    supplier_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    supplier_compare_at = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    supplier_sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    supplier_sale_start = models.DateTimeField(null=True, blank=True)
    supplier_sale_end = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    max_order_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Optional per-order cap for fairness. Leave blank for no cap beyond stock.',
    )
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    weight_oz = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    length_in = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    width_in = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    height_in = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    chest_width_in = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    body_length_in = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    sleeve_length_in = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    origin_country = models.CharField(max_length=2, default='US')
    hs_code = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product__name', 'sort_order', '-is_default', 'title']
        constraints = [
            models.UniqueConstraint(fields=['product'], condition=models.Q(is_default=True), name='unique_default_variant_per_product'),
        ]

    def __str__(self) -> str:
        return f'{self.product.name} / {self.title}'

    def save(self, *args, **kwargs):
        if not self.size_label and self.title:
            self.size_label = display_size_label_for(self.title)
        derived_order = sort_order_for_size(self.size_label or self.title)
        if derived_order is not None and self.sort_order == 0:
            self.sort_order = derived_order
        if self.product.default_source != Product.Source.INTERNAL and getattr(settings, 'AUTO_ENFORCE_EXTERNAL_RETAIL_FLOOR', True):
            recommended_price = self.recommended_retail_price
            current_price = self.price if self.price is not None else Decimal('0.00')
            if recommended_price is not None and current_price < recommended_price:
                self.price = recommended_price
        super().save(*args, **kwargs)

    @property
    def supplier_unit_cost(self) -> Decimal | None:
        now = timezone.now()
        if self.supplier_sale_price is not None:
            sale_started = self.supplier_sale_start is None or self.supplier_sale_start <= now
            sale_active = self.supplier_sale_end is None or self.supplier_sale_end >= now
            if sale_started and sale_active:
                return self.supplier_sale_price
        return self.supplier_price

    @property
    def recommended_retail_price(self) -> Decimal | None:
        return calculate_external_retail_price(self.product.default_source, self.supplier_unit_cost)

    @property
    def effective_max_order_quantity(self) -> int:
        if self.max_order_quantity is None:
            return self.stock_quantity
        return min(self.stock_quantity, self.max_order_quantity)

    @property
    def display_size_label(self) -> str:
        return self.size_label or self.title

    @property
    def has_size_measurements(self) -> bool:
        return any(
            value is not None
            for value in (self.chest_width_in, self.body_length_in, self.sleeve_length_in)
        )


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
        """Ensure max 10 images per product."""
        if self.pk is None:  # Only check for new images
            existing_count = ProductImage.objects.filter(product=self.product).count()
            if existing_count >= 10:
                from django.core.exceptions import ValidationError
                raise ValidationError('Maximum 10 images per product.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ProductVideo(models.Model):
    """Up to 2 videos per product for showcase/demos."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='videos')
    video = models.FileField(
        upload_to='products/videos/',
        help_text='Supported formats: MP4, WebM, Ogg (max 100MB)'
    )
    thumbnail = models.ImageField(upload_to='products/video_thumbnails/', blank=True, null=True)
    title = models.CharField(max_length=255, default='Product video')
    sort_order = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self) -> str:
        return f'Video: {self.product.name}'

    def clean(self):
        if self.pk is None:
            existing_count = ProductVideo.objects.filter(product=self.product).count()
            if existing_count >= 2:
                from django.core.exceptions import ValidationError
                raise ValidationError('Maximum 2 videos per product.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


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


class StoreSettings(models.Model):
    name = models.CharField(max_length=120, default='TG11 Shop')
    tagline = models.CharField(max_length=255, default='Products, checkout, and fulfillment in one place.')
    motd = models.CharField(max_length=255, default='TG11 Shop control deck: products, checkout, and fulfillment in one place.')
    support_email = models.EmailField(default='support@shop.tg11.org')
    footer_text = models.CharField(
        max_length=255,
        default='Payments run through Stripe Checkout. Fulfillment jobs queue after payment.',
    )
    logo = models.ImageField(upload_to='store/branding/', blank=True)
    favicon = models.ImageField(upload_to='store/branding/', blank=True)
    social_image = models.ImageField(upload_to='store/branding/', blank=True)
    free_shipping_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('100.00'))
    currency = models.CharField(max_length=8, default='usd')
    order_prefix = models.CharField(max_length=12, default='TG11')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Store settings'
        verbose_name_plural = 'Store settings'

    def __str__(self) -> str:
        return self.name

    @classmethod
    def current(cls):
        settings_obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'name': getattr(settings, 'STORE_NAME', 'TG11 Shop'),
                'currency': getattr(settings, 'STRIPE_CURRENCY', 'usd'),
            },
        )
        return settings_obj
