from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from config.views import healthcheck

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.account.urls')),
    path('account/', include(('accounts.urls', 'accounts'), namespace='accounts')),
    path('cart/', include(('cart.urls', 'cart'), namespace='cart')),
    path('checkout/', include(('checkout.urls', 'checkout'), namespace='checkout')),
    path('orders/', include(('orders.urls', 'orders'), namespace='orders')),
    path('payments/', include(('payments.urls', 'payments'), namespace='payments')),
    path('connectors/', include(('connectors.urls', 'connectors'), namespace='connectors')),
    path('dashboard/', include(('dashboard.urls', 'dashboard'), namespace='dashboard')),
    path('health/', healthcheck, name='healthcheck'),
    path('', include(('catalog.urls', 'catalog'), namespace='catalog')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif getattr(settings, 'SERVE_MEDIA', False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
