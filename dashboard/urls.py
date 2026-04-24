from django.urls import path

from .views import channel_create, dashboard_home, listing_create, page_create, product_create, storefront_manager

app_name = 'dashboard'

urlpatterns = [
    path('', dashboard_home, name='home'),
    path('manage/', storefront_manager, name='manage'),
    path('manage/products/new/', product_create, name='product_create'),
    path('manage/pages/new/', page_create, name='page_create'),
    path('manage/channels/new/', channel_create, name='channel_create'),
    path('manage/listings/new/', listing_create, name='listing_create'),
]
