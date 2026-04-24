from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.db import models


class Order(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PENDING_PAYMENT = 'pending_payment', 'Pending payment'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'
        FULFILLED = 'fulfilled', 'Fulfilled'
        CANCELLED = 'cancelled', 'Cancelled'

    class FulfillmentStatus(models.TextChoices):
        UNSUBMITTED = 'unsubmitted', 'Unsubmitted'
        QUEUED = 'queued', 'Queued'
        IN_PROGRESS = 'in_progress', 'In progress'
        SHIPPED = 'shipped', 'Shipped'
        DELIVERED = 'delivered', 'Delivered'

    class Source(models.TextChoices):
        INTERNAL = 'internal', 'Internal'
        ETSY = 'etsy', 'Etsy'
        POPCUSTOMS = 'popcustoms', 'PopCustoms'

    class SyncState(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SYNCED = 'synced', 'Synced'
        ERROR = 'error', 'Error'
        NOT_APPLICABLE = 'not_applicable', 'Not applicable'

    number = models.CharField(max_length=24, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    cart = models.ForeignKey('cart.Cart', on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    email = models.EmailField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_PAYMENT)
    fulfillment_status = models.CharField(max_length=20, choices=FulfillmentStatus.choices, default=FulfillmentStatus.UNSUBMITTED)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.INTERNAL)
    external_order_id = models.CharField(max_length=255, blank=True)
    external_reference = models.CharField(max_length=255, blank=True)
    connector_slug = models.CharField(max_length=64, blank=True)
    sync_state = models.CharField(max_length=20, choices=SyncState.choices, default=SyncState.NOT_APPLICABLE)
    shipping_address = models.JSONField(default=dict, blank=True)
    billing_address = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    tax_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    shipping_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-placed_at']

    def __str__(self) -> str:
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = f'TG11-{uuid4().hex[:10].upper()}'
        super().save(*args, **kwargs)

    @property
    def fulfillment_label(self) -> str:
        return self.get_source_display()


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('catalog.Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='order_items')
    variant = models.ForeignKey('catalog.ProductVariant', on_delete=models.SET_NULL, null=True, blank=True, related_name='order_items')
    title = models.CharField(max_length=255)
    sku = models.CharField(max_length=64, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    source = models.CharField(max_length=20, choices=Order.Source.choices, default=Order.Source.INTERNAL)
    external_listing_id = models.CharField(max_length=255, blank=True)
    custom_request = models.TextField(blank=True)

    def __str__(self) -> str:
        return f'{self.title} x {self.quantity}'

    @property
    def line_total(self) -> Decimal:
        return (self.unit_price * self.quantity).quantize(Decimal('0.01'))


class FulfillmentUpdate(models.Model):
    """Tracks fulfillment status changes and shipping details."""
    
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='fulfillment_updates')
    status = models.CharField(
        max_length=20,
        choices=Order.FulfillmentStatus.choices,
    )
    tracking_number = models.CharField(max_length=255, blank=True, help_text='Carrier tracking number (e.g., UPS, FedEx, USPS)')
    carrier = models.CharField(
        max_length=50,
        blank=True,
        choices=[
            ('ups', 'UPS'),
            ('fedex', 'FedEx'),
            ('usps', 'USPS'),
            ('dhl', 'DHL'),
            ('other', 'Other'),
        ]
    )
    tracking_url = models.URLField(blank=True, help_text='Direct link to tracking information')
    estimated_delivery = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, help_text='Additional notes for the customer')
    email_sent = models.BooleanField(default=False, help_text='Whether notification email has been sent')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='fulfillment_updates_created')

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Fulfillment updates'

    def __str__(self) -> str:
        return f'{self.order.number} - {self.get_status_display()} ({self.created_at.date()})'

    def get_tracking_url_display(self) -> str:
        """Generate tracking URL if not provided but we have tracking number and carrier."""
        if self.tracking_url:
            return self.tracking_url
        if not self.tracking_number or not self.carrier:
            return ''
        
        carriers = {
            'ups': f'https://tracking.ups.com/track?tracknum={self.tracking_number}',
            'fedex': f'https://tracking.fedex.com/en/track/{self.tracking_number}',
            'usps': f'https://tools.usps.com/go/TrackConfirmAction?tLabels={self.tracking_number}',
            'dhl': f'https://www.dhl.com/en/en/express/tracking.html?AWB={self.tracking_number}',
        }
        return carriers.get(self.carrier, '')

