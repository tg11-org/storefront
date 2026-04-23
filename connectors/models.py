from django.db import models


class ChannelAccount(models.Model):
    class Provider(models.TextChoices):
        ETSY = 'etsy', 'Etsy'
        POPCUSTOMS = 'popcustoms', 'PopCustoms'

    provider = models.CharField(max_length=32, choices=Provider.choices)
    name = models.CharField(max_length=255)
    account_identifier = models.CharField(max_length=255)
    access_token = models.CharField(max_length=255, blank=True)
    refresh_token = models.CharField(max_length=255, blank=True)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    sync_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('provider', 'account_identifier')

    def __str__(self) -> str:
        return f'{self.get_provider_display()} - {self.name}'


class ExternalListing(models.Model):
    class SyncState(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SYNCED = 'synced', 'Synced'
        ERROR = 'error', 'Error'

    provider = models.CharField(max_length=32, choices=ChannelAccount.Provider.choices)
    channel_account = models.ForeignKey(ChannelAccount, on_delete=models.CASCADE, related_name='listings')
    product = models.ForeignKey('catalog.Product', on_delete=models.CASCADE, related_name='external_listings')
    variant = models.ForeignKey('catalog.ProductVariant', on_delete=models.CASCADE, related_name='external_listings', null=True, blank=True)
    external_listing_id = models.CharField(max_length=255)
    external_product_id = models.CharField(max_length=255, blank=True)
    external_variant_id = models.CharField(max_length=255, blank=True)
    listing_url = models.URLField(blank=True)
    sync_state = models.CharField(max_length=20, choices=SyncState.choices, default=SyncState.PENDING)
    metadata = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('provider', 'external_listing_id')

    def __str__(self) -> str:
        return f'{self.product.name} -> {self.provider}:{self.external_listing_id}'


class ExternalOrder(models.Model):
    provider = models.CharField(max_length=32, choices=ChannelAccount.Provider.choices)
    channel_account = models.ForeignKey(ChannelAccount, on_delete=models.CASCADE, related_name='orders')
    order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='external_records')
    external_order_id = models.CharField(max_length=255)
    external_status = models.CharField(max_length=64, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('provider', 'external_order_id')

    def __str__(self) -> str:
        return f'{self.provider}:{self.external_order_id}'


class SyncJob(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED = 'failed', 'Failed'

    provider = models.CharField(max_length=32, choices=ChannelAccount.Provider.choices)
    target_type = models.CharField(max_length=64)
    target_id = models.CharField(max_length=64)
    action = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payload = models.JSONField(default=dict, blank=True)
    log = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.provider} {self.action} ({self.status})'
