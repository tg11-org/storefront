from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render
from django.urls import reverse

from catalog.models import Product, StorePage
from connectors.models import ChannelAccount, ExternalListing
from connectors.models import SyncJob
from orders.models import Order
from payments.models import PaymentRecord


@staff_member_required
def dashboard_home(request):
    paid_orders = Order.objects.filter(status=Order.Status.PAID)
    gross_sales = sum((order.grand_total for order in paid_orders), Decimal('0.00'))
    metrics = {
        'order_count': Order.objects.count(),
        'gross_sales': gross_sales,
        'connector_jobs': SyncJob.objects.count(),
        'successful_payments': PaymentRecord.objects.filter(status=PaymentRecord.Status.SUCCEEDED).count(),
    }
    return render(request, 'dashboard/home.html', {'metrics': metrics, 'recent_orders': Order.objects.all()[:10], 'recent_jobs': SyncJob.objects.all()[:10]})


def _is_superuser(user):
    return user.is_active and user.is_superuser


@user_passes_test(_is_superuser)
def storefront_manager(request):
    stats = {
        'products': Product.objects.count(),
        'published_pages': StorePage.objects.filter(is_published=True).count(),
        'channel_accounts': ChannelAccount.objects.filter(is_active=True).count(),
        'external_listings': ExternalListing.objects.count(),
        'queued_jobs': SyncJob.objects.filter(status=SyncJob.Status.PENDING).count(),
        'paid_orders': Order.objects.filter(status=Order.Status.PAID).count(),
    }
    shortcuts = [
        {'label': 'Add product', 'url': reverse('admin:catalog_product_add'), 'description': 'Create a product, variants, images, and fulfillment source.'},
        {'label': 'Manage products', 'url': reverse('admin:catalog_product_changelist'), 'description': 'Edit catalog items and mark featured products.'},
        {'label': 'Add page', 'url': reverse('admin:catalog_storepage_add'), 'description': 'Create a content page and link orderable products to it.'},
        {'label': 'Manage pages', 'url': reverse('admin:catalog_storepage_changelist'), 'description': 'Publish landing pages, product collections, and info pages.'},
        {'label': 'Channel accounts', 'url': reverse('admin:connectors_channelaccount_changelist'), 'description': 'Configure Etsy, PopCustoms, and future vendor accounts.'},
        {'label': 'External listings', 'url': reverse('admin:connectors_externallisting_changelist'), 'description': 'Map local products and variants to vendor listing IDs.'},
        {'label': 'Orders', 'url': reverse('admin:orders_order_changelist'), 'description': 'Review paid orders, fulfillment state, and vendor references.'},
        {'label': 'Fulfillment jobs', 'url': reverse('admin:connectors_syncjob_changelist'), 'description': 'Track queued connector work after payment.'},
    ]
    return render(request, 'dashboard/manage.html', {'stats': stats, 'shortcuts': shortcuts})
