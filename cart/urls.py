from django.urls import path

from .views import add_to_cart, cart_detail, remove_cart_item, update_cart_item

app_name = 'cart'

urlpatterns = [
    path('', cart_detail, name='detail'),
    path('add/<slug:slug>/', add_to_cart, name='add'),
    path('item/<int:pk>/update/', update_cart_item, name='update_item'),
    path('item/<int:pk>/remove/', remove_cart_item, name='remove_item'),
]
