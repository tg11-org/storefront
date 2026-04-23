from django.contrib import admin

from .models import ChannelAccount, ExternalListing, ExternalOrder, SyncJob


@admin.register(ChannelAccount)
class ChannelAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'account_identifier', 'is_active', 'sync_enabled')
    list_filter = ('provider', 'is_active', 'sync_enabled')
    search_fields = ('name', 'account_identifier')


@admin.register(ExternalListing)
class ExternalListingAdmin(admin.ModelAdmin):
    list_display = ('product', 'provider', 'external_listing_id', 'sync_state', 'last_synced_at')
    list_filter = ('provider', 'sync_state')
    search_fields = ('product__name', 'external_listing_id')


@admin.register(ExternalOrder)
class ExternalOrderAdmin(admin.ModelAdmin):
    list_display = ('provider', 'external_order_id', 'external_status', 'last_synced_at')
    list_filter = ('provider',)
    search_fields = ('external_order_id', 'order__number')


@admin.register(SyncJob)
class SyncJobAdmin(admin.ModelAdmin):
    list_display = ('provider', 'action', 'target_type', 'target_id', 'status', 'created_at')
    list_filter = ('provider', 'status', 'action')
    search_fields = ('target_id', 'log')
