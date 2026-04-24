from django.urls import path

from .views import dashboard_home, storefront_manager

app_name = 'dashboard'

urlpatterns = [
    path('', dashboard_home, name='home'),
    path('manage/', storefront_manager, name='manage'),
]
