from django.urls import path

from .views import CheckoutCancelView, CheckoutSuccessView, CheckoutView

app_name = 'checkout'

urlpatterns = [
    path('', CheckoutView.as_view(), name='start'),
    path('success/', CheckoutSuccessView.as_view(), name='success'),
    path('cancel/', CheckoutCancelView.as_view(), name='cancel'),
]
