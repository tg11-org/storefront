from django.urls import path

from .views import (
    channel_create, dashboard_home, listing_create, page_create, product_create,
    storefront_manager, orders_manage, order_fulfill, orders_bulk_action,
    resend_order_confirmation, resend_fulfillment_email,
)

app_name = 'dashboard'

urlpatterns = [
    path('', dashboard_home, name='home'),
    path('manage/', storefront_manager, name='manage'),
    path('manage/products/new/', product_create, name='product_create'),
    path('manage/pages/new/', page_create, name='page_create'),
    path('manage/channels/new/', channel_create, name='channel_create'),
    path('manage/listings/new/', listing_create, name='listing_create'),
    path('manage/orders/', orders_manage, name='orders_manage'),
    path('manage/orders/<str:order_number>/', order_fulfill, name='order_fulfill'),
    path('manage/orders/<str:order_number>/resend-confirmation/', resend_order_confirmation, name='resend_order_confirmation'),
    path('manage/orders/updates/<int:update_id>/resend-email/', resend_fulfillment_email, name='resend_fulfillment_email'),
    path('manage/orders/bulk/action/', orders_bulk_action, name='orders_bulk_action'),
]
