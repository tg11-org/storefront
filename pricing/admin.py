from django.contrib import admin

from .models import Coupon, CouponRedemption, Promotion, PromotionScope, ShippingMethod, ShippingRateRule, ShippingWebhookEvent, ShippingZone


class PromotionScopeInline(admin.TabularInline):
    model = PromotionScope
    extra = 1
    filter_horizontal = ('products', 'pages')


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('name', 'promotion_type', 'value', 'active', 'priority', 'combinable', 'source', 'updated_at')
    list_filter = ('promotion_type', 'active', 'combinable', 'source')
    search_fields = ('name',)
    inlines = [PromotionScopeInline]

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'active', 'min_subtotal', 'max_total_uses', 'max_uses_per_customer', 'first_order_only', 'combinable')
    list_filter = ('active', 'first_order_only', 'combinable')
    search_fields = ('code',)
    filter_horizontal = ('promotions',)

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ('coupon', 'user', 'order', 'email', 'created_at')
    search_fields = ('coupon__code', 'order__number', 'email')


@admin.register(ShippingZone)
class ShippingZoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'countries', 'active')
    list_filter = ('active',)


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ('name', 'carrier', 'active', 'estimated_min_days', 'estimated_max_days')
    list_filter = ('carrier', 'active')


@admin.register(ShippingRateRule)
class ShippingRateRuleAdmin(admin.ModelAdmin):
    list_display = ('zone', 'method', 'rate_type', 'amount', 'min_weight_oz', 'max_weight_oz', 'min_subtotal', 'max_subtotal', 'fallback', 'active')
    list_filter = ('rate_type', 'fallback', 'active', 'zone', 'method')


@admin.register(ShippingWebhookEvent)
class ShippingWebhookEventAdmin(admin.ModelAdmin):
    list_display = ('provider', 'event_type', 'event_id', 'order', 'processed', 'received_at')
    list_filter = ('provider', 'event_type', 'processed', 'received_at')
    search_fields = ('event_id', 'order__number', 'message')
    readonly_fields = ('provider', 'event_id', 'event_type', 'order', 'payload', 'processed', 'message', 'received_at')
