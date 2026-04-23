from django.contrib import admin

from .models import PaymentRecord, SavedPaymentMethodRef


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ('provider', 'status', 'amount', 'currency', 'order', 'created_at')
    list_filter = ('provider', 'status', 'currency')
    search_fields = ('stripe_payment_intent_id', 'stripe_checkout_session_id', 'order__number', 'user__email')


@admin.register(SavedPaymentMethodRef)
class SavedPaymentMethodRefAdmin(admin.ModelAdmin):
    list_display = ('user', 'brand', 'last4', 'exp_month', 'exp_year', 'is_default')
    search_fields = ('user__email', 'stripe_payment_method_id', 'stripe_customer_id')
