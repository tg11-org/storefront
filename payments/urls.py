from django.urls import path

from .views import add_payment_method, setup_success, stripe_webhook

app_name = 'payments'

urlpatterns = [
    path('methods/add/', add_payment_method, name='add_method'),
    path('methods/success/', setup_success, name='setup_success'),
    path('webhooks/stripe', stripe_webhook),
    path('webhooks/stripe/', stripe_webhook, name='stripe_webhook'),
]
