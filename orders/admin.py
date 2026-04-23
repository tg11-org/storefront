from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('number', 'email', 'status', 'source', 'sync_state', 'grand_total', 'placed_at')
    list_filter = ('status', 'source', 'sync_state', 'fulfillment_status')
    search_fields = ('number', 'email', 'external_order_id', 'stripe_payment_intent_id')
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'title', 'quantity', 'unit_price', 'source')
