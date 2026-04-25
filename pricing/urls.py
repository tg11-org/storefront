from django.urls import path

from .views import easypost_webhook, shippo_webhook

app_name = 'pricing'

urlpatterns = [
    path('easypost/', easypost_webhook, name='easypost_webhook'),
    path('shippo/', shippo_webhook, name='shippo_webhook'),
]
