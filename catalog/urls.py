from django.urls import path

from .views import HomeView, ProductDetailView, ProductListView, ProductOEmbedView, StorePageDetailView

app_name = 'catalog'

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('products/', ProductListView.as_view(), name='product_list'),
    path('products/<slug:slug>/', ProductDetailView.as_view(), name='product_detail'),
    path('oembed/', ProductOEmbedView.as_view(), name='product_oembed'),
    path('pages/<slug:slug>/', StorePageDetailView.as_view(), name='page_detail'),
]
