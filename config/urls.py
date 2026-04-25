import re

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as _serve_static

from config.views import favicon, healthcheck

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
    path('favicon.ico', favicon, {'filename': 'favicon.ico'}, name='favicon_ico'),
    path('favicon.png', favicon, {'filename': 'favicon.png'}, name='favicon_png'),
    path('', include(('catalog.urls', 'catalog'), namespace='catalog')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif getattr(settings, 'SERVE_MEDIA', False):
    # Django's static() helper silently returns [] when DEBUG=False, so we
    # build the URL pattern directly to actually serve user-uploaded media.
    urlpatterns += [
        re_path(
            r'^%s(?P<path>.*)$' % re.escape(settings.MEDIA_URL.lstrip('/')),
            _serve_static,
            kwargs={'document_root': settings.MEDIA_ROOT},
        )
    ]
