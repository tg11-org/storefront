from django.urls import path

from .views import foxpay_webhook, paypal_webhook, add_payment_method, setup_success, stripe_webhook

app_name = 'payments'

urlpatterns = [
    path('methods/add/', add_payment_method, name='add_method'),
    path('methods/success/', setup_success, name='setup_success'),
    path('webhooks/stripe', stripe_webhook),
    path('webhooks/stripe/', stripe_webhook, name='stripe_webhook'),
    path('webhooks/foxpay/', foxpay_webhook, name='foxpay_webhook'),
    path('webhooks/paypal/', paypal_webhook, name='paypal_webhook'),
]
