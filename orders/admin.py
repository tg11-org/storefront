from django.contrib import admin

from .models import Order, OrderItem, FulfillmentUpdate


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class FulfillmentUpdateInline(admin.TabularInline):
    model = FulfillmentUpdate
    extra = 0
    fields = ('status', 'tracking_number', 'carrier', 'estimated_delivery', 'email_sent', 'created_at', 'created_by')
    readonly_fields = ('created_at', 'created_by')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('number', 'email', 'status', 'fulfillment_status', 'source', 'grand_total', 'placed_at')
    list_filter = ('status', 'fulfillment_status', 'source')
    search_fields = ('number', 'email', 'external_order_id', 'stripe_payment_intent_id')
    inlines = [OrderItemInline, FulfillmentUpdateInline]
    readonly_fields = ('number', 'placed_at', 'updated_at')


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'title', 'quantity', 'unit_price', 'source')


@admin.register(FulfillmentUpdate)
class FulfillmentUpdateAdmin(admin.ModelAdmin):
    list_display = ('order', 'status', 'tracking_number', 'carrier', 'email_sent', 'created_at')
    list_filter = ('status', 'carrier', 'email_sent', 'created_at')
    search_fields = ('order__number', 'tracking_number')
    readonly_fields = ('created_at', 'created_by')
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
