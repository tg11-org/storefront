from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.db.models import Q

from catalog.models import Product, ProductImage, ProductVideo, StorePage
from connectors.models import ChannelAccount, ExternalListing
from connectors.models import SyncJob
from connectors.services import import_channel_listings, push_external_inventory, sync_external_listing
from orders.models import Order, FulfillmentUpdate
from orders.services import (
    create_fulfillment_update,
    mark_order_refunded,
    mark_order_return_requested,
    send_fulfillment_notification,
    send_order_confirmation_email,
)
from payments.models import PaymentRecord

from .forms import (
    ChannelAccountCreateForm, DefaultVariantForm, ExternalListingCreateForm, 
    ProductCreateForm, StorePageCreateForm, FulfillmentUpdateForm, OrderFilterForm,
    BulkOrderActionForm, OrderRefundForm
)


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
        {'label': 'Manage Orders', 'url': reverse('dashboard:orders_manage'), 'description': 'Update fulfillment status, track shipments, and process refunds.'},
        {'label': 'Add product', 'url': reverse('dashboard:product_create'), 'description': 'Create a product with its first orderable variant.'},
        {'label': 'Manage products', 'url': reverse('admin:catalog_product_changelist'), 'description': 'Edit catalog items and mark featured products.'},
        {'label': 'Add page', 'url': reverse('dashboard:page_create'), 'description': 'Publish a page and link products to it.'},
        {'label': 'Manage pages', 'url': reverse('admin:catalog_storepage_changelist'), 'description': 'Publish landing pages, product collections, and info pages.'},
        {'label': 'Store settings', 'url': reverse('admin:catalog_storesettings_changelist'), 'description': 'Edit brand, MOTD, support email, footer, social image, currency, and order prefix.'},
        {'label': 'Promotions', 'url': reverse('admin:pricing_promotion_changelist'), 'description': 'Create sales, discounts, and free shipping rules.'},
        {'label': 'Coupons', 'url': reverse('admin:pricing_coupon_changelist'), 'description': 'Manage coupon codes, limits, and stacking behavior.'},
        {'label': 'Shipping rates', 'url': reverse('admin:pricing_shippingraterule_changelist'), 'description': 'Configure domestic, international, and fallback shipping rates.'},
        {'label': 'Add channel', 'url': reverse('dashboard:channel_create'), 'description': 'Connect an Etsy or PopCustoms account profile.'},
        {'label': 'Link listing', 'url': reverse('dashboard:listing_create'), 'description': 'Map local products and variants to vendor listing IDs.'},
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
    product_form = ProductCreateForm(request.POST or None, request.FILES or None, prefix='product')
    variant_form = DefaultVariantForm(request.POST or None, prefix='variant', initial={'title': 'Default', 'is_active': True})
    if request.method == 'POST' and product_form.is_valid() and variant_form.is_valid():
        product = product_form.save()
        variant = variant_form.save(commit=False)
        variant.product = product
        variant.is_default = True
        variant.save()

        for index, field_name in enumerate([
            'image_1', 'image_2', 'image_3', 'image_4', 'image_5',
            'image_6', 'image_7', 'image_8', 'image_9', 'image_10',
        ]):
            image_file = product_form.cleaned_data.get(field_name)
            if image_file:
                ProductImage.objects.create(
                    product=product,
                    image=image_file,
                    sort_order=index,
                    alt_text=product.name,
                )

        for index, suffix in enumerate(['1', '2']):
            video_file = product_form.cleaned_data.get(f'video_file_{suffix}')
            if video_file:
                ProductVideo.objects.create(
                    product=product,
                    video=video_file,
                    thumbnail=product_form.cleaned_data.get(f'video_thumbnail_{suffix}'),
                    title=product_form.cleaned_data.get(f'video_title_{suffix}') or f'{product.name} video {suffix}',
                    sort_order=index,
                )

        messages.success(request, f'{product.name} was created.')
        return redirect(product.get_absolute_url())
    return render(
        request,
        'dashboard/product_form.html',
        {'product_form': product_form, 'variant_form': variant_form},
    )


@user_passes_test(_is_superuser)
def page_create(request):
    form = StorePageCreateForm(request.POST or None, request.FILES or None)
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
        {'name': 'PopCustoms', 'details': 'Use TG11 as the account identifier. The API key and order endpoint can stay in .env, so config JSON can be empty unless PopCustoms gives extra store settings.'},
        {'name': 'Etsy', 'details': 'Put the keystring and shared secret in .env. Use your numeric shop ID as the account identifier or as {"shop_id": "..."} in config JSON, then add OAuth tokens when the connect flow is ready.'},
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


@user_passes_test(_is_superuser)
def channel_sync(request, channel_id):
    if request.method != 'POST':
        return redirect('dashboard:manage')
    channel = get_object_or_404(ChannelAccount, pk=channel_id)
    action = request.POST.get('action')
    try:
        if action == 'import_listings':
            listings = import_channel_listings(channel)
            messages.success(request, f'Imported {len(listings)} listing(s) from {channel.name}.')
        elif action == 'push_listings':
            count = 0
            for listing in ExternalListing.objects.filter(channel_account=channel).select_related('channel_account', 'product', 'variant'):
                sync_external_listing(listing)
                count += 1
            messages.success(request, f'Pushed {count} listing(s) to {channel.name}.')
        elif action == 'push_inventory':
            count = 0
            for listing in ExternalListing.objects.filter(channel_account=channel).select_related('channel_account', 'product', 'variant'):
                push_external_inventory(listing)
                count += 1
            messages.success(request, f'Pushed inventory for {count} listing(s) to {channel.name}.')
        else:
            messages.error(request, 'Unknown channel sync action.')
    except Exception as exc:
        messages.error(request, f'{channel.name} sync failed: {exc}')
    return redirect('dashboard:manage')


@user_passes_test(_is_superuser)
def listing_sync(request, listing_id):
    if request.method != 'POST':
        return redirect('dashboard:manage')
    listing = get_object_or_404(ExternalListing.objects.select_related('channel_account', 'product', 'variant'), pk=listing_id)
    action = request.POST.get('action')
    try:
        if action == 'push_listing':
            sync_external_listing(listing)
            messages.success(request, f'Pushed {listing.product.name} to {listing.channel_account.name}.')
        elif action == 'push_inventory':
            push_external_inventory(listing)
            messages.success(request, f'Pushed inventory for {listing.product.name}.')
        else:
            messages.error(request, 'Unknown listing sync action.')
    except Exception as exc:
        messages.error(request, f'{listing.product.name} sync failed: {exc}')
    return redirect('dashboard:manage')


@staff_member_required
def orders_manage(request):
    """List and filter orders for fulfillment management."""
    orders = Order.objects.prefetch_related('items', 'fulfillment_updates').all()
    filter_form = OrderFilterForm(request.GET or None)
    
    # Apply filters
    if filter_form.is_valid():
        if filter_form.cleaned_data.get('status'):
            orders = orders.filter(status=filter_form.cleaned_data['status'])
        if filter_form.cleaned_data.get('fulfillment_status'):
            orders = orders.filter(fulfillment_status=filter_form.cleaned_data['fulfillment_status'])
        if filter_form.cleaned_data.get('source'):
            orders = orders.filter(source=filter_form.cleaned_data['source'])
        if filter_form.cleaned_data.get('search'):
            search_term = filter_form.cleaned_data['search']
            orders = orders.filter(
                Q(number__icontains=search_term) | Q(email__icontains=search_term)
            )
    
    # Calculate stats
    stats = {
        'total_orders': Order.objects.count(),
        'paid_unfulfilled': Order.objects.filter(
            status=Order.Status.PAID,
            fulfillment_status=Order.FulfillmentStatus.UNSUBMITTED
        ).count(),
        'in_transit': Order.objects.filter(
            fulfillment_status__in=[
                Order.FulfillmentStatus.QUEUED,
                Order.FulfillmentStatus.IN_PROGRESS,
                Order.FulfillmentStatus.SHIPPED,
            ]
        ).count(),
        'delivered': Order.objects.filter(fulfillment_status=Order.FulfillmentStatus.DELIVERED).count(),
    }
    
    context = {
        'orders': orders.order_by('-placed_at'),
        'filter_form': filter_form,
        'stats': stats,
    }
    return render(request, 'dashboard/orders_manage.html', context)


@staff_member_required
def order_fulfill(request, order_number):
    """Detailed order view with fulfillment status updates."""
    order = get_object_or_404(Order, number=order_number)
    fulfillment_form = FulfillmentUpdateForm(request.POST or None, prefix='fulfill')
    refund_form = OrderRefundForm(request.POST or None, prefix='refund') if request.POST and 'refund-reason' in request.POST else None
    return_form = OrderRefundForm(request.POST or None, prefix='return') if request.POST and 'return-reason' in request.POST else None
    
    if request.method == 'POST':
        # Handle fulfillment update
        if 'fulfill-status' in request.POST and fulfillment_form.is_valid():
            fulfillment_update = fulfillment_form.save(commit=False)
            fulfillment_update.order = order
            fulfillment_update.created_by = request.user
            fulfillment_update.save()
            
            # Send notification email
            send_fulfillment_notification(fulfillment_update)
            
            messages.success(request, f'Order status updated to {fulfillment_update.get_status_display()}')
            return redirect('dashboard:order_fulfill', order_number=order.number)
        
        # Handle refund
        if 'refund-confirm' in request.POST and refund_form and refund_form.is_valid():
            if refund_form.cleaned_data['confirm']:
                mark_order_refunded(
                    order,
                    reason=refund_form.cleaned_data['reason'],
                    created_by=request.user
                )
                messages.success(request, f'Order {order.number} has been marked as refunded')
                return redirect('dashboard:order_fulfill', order_number=order.number)
        
        # Handle return request
        if 'return-confirm' in request.POST and return_form and return_form.is_valid():
            if return_form.cleaned_data['confirm']:
                mark_order_return_requested(
                    order,
                    reason=return_form.cleaned_data['reason'],
                    created_by=request.user
                )
                messages.success(request, f'Return initiated for order {order.number}')
                return redirect('dashboard:order_fulfill', order_number=order.number)
    
    context = {
        'order': order,
        'fulfillment_form': fulfillment_form,
        'refund_form': refund_form,
        'return_form': return_form,
        'fulfillment_updates': order.fulfillment_updates.all(),
    }
    return render(request, 'dashboard/order_fulfill.html', context)


@staff_member_required
def resend_order_confirmation(request, order_number):
    """Resend order confirmation email from manage orders."""
    if request.method != 'POST':
        return redirect('dashboard:orders_manage')

    order = get_object_or_404(Order, number=order_number)
    if send_order_confirmation_email(order):
        messages.success(request, f'Order confirmation email sent for {order.number}.')
    else:
        messages.error(request, f'Unable to send order confirmation email for {order.number}.')

    return redirect(request.META.get('HTTP_REFERER') or 'dashboard:orders_manage')


@staff_member_required
def resend_fulfillment_email(request, update_id):
    """Resend fulfillment status email for a specific update."""
    if request.method != 'POST':
        return redirect('dashboard:orders_manage')

    fulfillment_update = get_object_or_404(FulfillmentUpdate.objects.select_related('order'), pk=update_id)
    if send_fulfillment_notification(fulfillment_update, force_resend=True):
        messages.success(request, f'Fulfillment email resent for {fulfillment_update.order.number}.')
    else:
        messages.error(request, f'Unable to resend fulfillment email for {fulfillment_update.order.number}.')

    return redirect(request.META.get('HTTP_REFERER') or 'dashboard:orders_manage')


@staff_member_required
def orders_bulk_action(request):
    """Handle bulk actions on multiple orders."""
    if request.method != 'POST':
        return redirect('dashboard:orders_manage')
    
    form = BulkOrderActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Invalid action request')
        return redirect('dashboard:orders_manage')
    
    order_ids = form.cleaned_data['order_ids'].split(',')
    action = form.cleaned_data['action']
    notes = form.cleaned_data.get('notes', '')
    orders = Order.objects.filter(id__in=order_ids)
    
    status_map = {
        'mark_queued': Order.FulfillmentStatus.QUEUED,
        'mark_in_progress': Order.FulfillmentStatus.IN_PROGRESS,
        'mark_shipped': Order.FulfillmentStatus.SHIPPED,
        'mark_delivered': Order.FulfillmentStatus.DELIVERED,
    }
    
    if action in status_map:
        new_status = status_map[action]
        updated_count = 0
        
        for order in orders:
            create_fulfillment_update(
                order,
                status=new_status,
                notes=notes,
                created_by=request.user,
                send_email=True
            )
            updated_count += 1
        
        messages.success(request, f'Updated {updated_count} order(s) to {Order.FulfillmentStatus(new_status).label}')
    
    return redirect('dashboard:orders_manage')
