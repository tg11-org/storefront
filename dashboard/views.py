from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect, render
from django.urls import reverse

from catalog.models import Product, StorePage
from connectors.models import ChannelAccount, ExternalListing
from connectors.models import SyncJob
from orders.models import Order
from payments.models import PaymentRecord

from .forms import ChannelAccountCreateForm, DefaultVariantForm, ExternalListingCreateForm, ProductCreateForm, StorePageCreateForm


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
        {'label': 'Add product', 'url': reverse('dashboard:product_create'), 'description': 'Create a product with its first orderable variant.'},
        {'label': 'Manage products', 'url': reverse('admin:catalog_product_changelist'), 'description': 'Edit catalog items and mark featured products.'},
        {'label': 'Add page', 'url': reverse('dashboard:page_create'), 'description': 'Publish a page and link products to it.'},
        {'label': 'Manage pages', 'url': reverse('admin:catalog_storepage_changelist'), 'description': 'Publish landing pages, product collections, and info pages.'},
        {'label': 'Add channel', 'url': reverse('dashboard:channel_create'), 'description': 'Connect an Etsy or PopCustoms account profile.'},
        {'label': 'Link listing', 'url': reverse('dashboard:listing_create'), 'description': 'Map local products and variants to vendor listing IDs.'},
        {'label': 'Orders', 'url': reverse('admin:orders_order_changelist'), 'description': 'Review paid orders, fulfillment state, and vendor references.'},
        {'label': 'Fulfillment jobs', 'url': reverse('admin:connectors_syncjob_changelist'), 'description': 'Track queued connector work after payment.'},
    ]
    context = {
        'stats': stats,
        'shortcuts': shortcuts,
        'recent_products': Product.objects.prefetch_related('variants')[:6],
        'recent_pages': StorePage.objects.prefetch_related('products')[:6],
        'channel_accounts': ChannelAccount.objects.all()[:6],
        'external_listings': ExternalListing.objects.select_related('product', 'variant', 'channel_account')[:6],
    }
    return render(request, 'dashboard/manage.html', context)


@user_passes_test(_is_superuser)
def product_create(request):
    product_form = ProductCreateForm(request.POST or None, prefix='product')
    variant_form = DefaultVariantForm(request.POST or None, prefix='variant', initial={'title': 'Default', 'is_active': True})
    if request.method == 'POST' and product_form.is_valid() and variant_form.is_valid():
        product = product_form.save()
        variant = variant_form.save(commit=False)
        variant.product = product
        variant.is_default = True
        variant.save()
        messages.success(request, f'{product.name} was created.')
        return redirect(product.get_absolute_url())
    return render(
        request,
        'dashboard/product_form.html',
        {'product_form': product_form, 'variant_form': variant_form},
    )


@user_passes_test(_is_superuser)
def page_create(request):
    form = StorePageCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        page = form.save()
        messages.success(request, f'{page.title} was created.')
        return redirect(page.get_absolute_url() if page.is_published else 'dashboard:manage')
    return render(request, 'dashboard/model_form.html', {'form': form, 'title': 'Add page', 'eyebrow': 'Store pages', 'submit_label': 'Create page'})


@user_passes_test(_is_superuser)
def channel_create(request):
    form = ChannelAccountCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        channel = form.save()
        messages.success(request, f'{channel.name} channel account was created.')
        return redirect('dashboard:manage')
    provider_notes = [
        {'name': 'PopCustoms', 'details': 'Use the account or shop identifier from PopCustoms. API placement still needs the final PopCustoms contract before live auto-ordering.'},
        {'name': 'Etsy', 'details': 'Use your shop ID as config JSON, and OAuth tokens when you are ready to sync receipts or listing data.'},
    ]
    return render(
        request,
        'dashboard/channel_form.html',
        {'form': form, 'provider_notes': provider_notes},
    )


@user_passes_test(_is_superuser)
def listing_create(request):
    form = ExternalListingCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        listing = form.save()
        messages.success(request, f'{listing.product.name} was linked to {listing.get_provider_display()}.')
        return redirect('dashboard:manage')
    return render(
        request,
        'dashboard/model_form.html',
        {
            'form': form,
            'title': 'Link external listing',
            'eyebrow': 'Fulfillment mapping',
            'submit_label': 'Link listing',
            'lead': 'Map a TG11 product or variant to the vendor IDs used when paid orders queue fulfillment jobs.',
        },
    )
