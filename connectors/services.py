from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from catalog.models import Product, ProductVariant
from orders.models import Order

from .registry import get_connector
from .models import ChannelAccount, ExternalListing, SyncJob


def _provider_items(order: Order) -> dict[str, list[dict]]:
    items_by_provider: dict[str, list[dict]] = defaultdict(list)
    for item in order.items.select_related('product', 'variant'):
        if item.source == Order.Source.INTERNAL:
            continue
        listing = ExternalListing.objects.filter(
            provider=item.source,
            product=item.product,
            variant=item.variant,
        ).first()
        if not listing:
            listing = ExternalListing.objects.filter(
                provider=item.source,
                product=item.product,
                variant__isnull=True,
            ).first()
        items_by_provider[item.source].append(
            {
                'order_item_id': item.pk,
                'title': item.title,
                'sku': item.sku,
                'quantity': item.quantity,
                'unit_price': str(item.unit_price),
                'external_listing_id': item.external_listing_id or getattr(listing, 'external_listing_id', ''),
                'external_product_id': getattr(listing, 'external_product_id', ''),
                'external_variant_id': getattr(listing, 'external_variant_id', ''),
                'custom_request': item.custom_request,
            }
        )
    return dict(items_by_provider)


def queue_external_fulfillment_for_order(order: Order) -> list[SyncJob]:
    if order.status != Order.Status.PAID:
        return []

    jobs = []
    provider_items = _provider_items(order)
    for provider, items in provider_items.items():
        payload = {
            'order_number': order.number,
            'email': order.email,
            'shipping_address': order.shipping_address,
            'billing_address': order.billing_address,
            'items': items,
            'stripe_payment_intent_id': order.stripe_payment_intent_id,
        }
        channel_account = ChannelAccount.objects.filter(provider=provider, is_active=True, sync_enabled=True).first()
        existing = SyncJob.objects.filter(
            provider=provider,
            target_type='order',
            target_id=order.number,
            action='submit_order',
        ).first()
        if existing:
            existing.payload = payload
            existing.save(update_fields=['payload'])
            jobs.append(existing)
            continue

        if channel_account:
            job = SyncJob.objects.create(
                provider=provider,
                target_type='order',
                target_id=order.number,
                action='submit_order',
                status=SyncJob.Status.PENDING,
                payload=payload,
                log=f'Queued for {channel_account.name}.',
            )
        else:
            job = SyncJob.objects.create(
                provider=provider,
                target_type='order',
                target_id=order.number,
                action='submit_order',
                status=SyncJob.Status.FAILED,
                payload=payload,
                log='No active channel account is configured for this provider.',
                finished_at=timezone.now(),
            )
        jobs.append(job)

    if jobs:
        order.fulfillment_status = Order.FulfillmentStatus.QUEUED
        order.sync_state = Order.SyncState.PENDING if any(job.status == SyncJob.Status.PENDING for job in jobs) else Order.SyncState.ERROR
        order.save(update_fields=['fulfillment_status', 'sync_state', 'updated_at'])
    return jobs


def process_fulfillment_job(job: SyncJob) -> SyncJob:
    job.status = SyncJob.Status.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=['status', 'started_at'])

    try:
        channel_account = ChannelAccount.objects.filter(provider=job.provider, is_active=True, sync_enabled=True).first()
        if not channel_account:
            raise ValueError('No active channel account is configured for this provider.')
        order = Order.objects.get(number=job.target_id)
        connector = get_connector(channel_account)
        result = connector.submit_order(order, job.payload.get('items', []))
    except Exception as exc:
        job.status = SyncJob.Status.FAILED
        job.log = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'log', 'finished_at'])
        Order.objects.filter(number=job.target_id).update(sync_state=Order.SyncState.ERROR, updated_at=timezone.now())
        return job

    job.status = SyncJob.Status.SUCCEEDED
    job.log = str(result)
    job.finished_at = timezone.now()
    job.save(update_fields=['status', 'log', 'finished_at'])
    Order.objects.filter(number=job.target_id).update(sync_state=Order.SyncState.SYNCED, fulfillment_status=Order.FulfillmentStatus.IN_PROGRESS, updated_at=timezone.now())
    return job


def process_pending_fulfillment_jobs(limit: int = 20, provider: str | None = None) -> list[SyncJob]:
    jobs = SyncJob.objects.filter(status=SyncJob.Status.PENDING, action='submit_order').order_by('created_at')
    if provider:
        jobs = jobs.filter(provider=provider)
    return [process_fulfillment_job(job) for job in jobs[:limit]]


def _first(payload: dict, *keys: str, default=''):
    for key in keys:
        value = payload.get(key)
        if value not in (None, ''):
            return value
    return default


def _money(value, default='0.00') -> Decimal:
    if isinstance(value, dict):
        if value.get('amount') not in (None, '') and value.get('divisor'):
            try:
                return (Decimal(str(value['amount'])) / Decimal(str(value['divisor']))).quantize(Decimal('0.01'))
            except (InvalidOperation, ValueError, TypeError, ZeroDivisionError):
                return Decimal(default)
        value = value.get('amount') or value.get('value') or default
    if isinstance(value, list) and value:
        value = _first(value[0], 'amount', 'value', default=default) if isinstance(value[0], dict) else value[0]
    try:
        return Decimal(str(value or default)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _quantity(value, default=0) -> int:
    try:
        return max(0, int(value if value not in (None, '') else default))
    except (TypeError, ValueError):
        return default


def _unique_slug(name: str, external_id: str) -> str:
    base = slugify(name)[:220] or f'imported-{external_id}'
    slug = base
    counter = 2
    while Product.objects.filter(slug=slug).exists():
        slug = f'{base[:220 - len(str(counter)) - 1]}-{counter}'
        counter += 1
    return slug


def _unique_sku(sku: str, external_id: str, *, exclude_pk: int | None = None) -> str:
    base = (sku or f'IMPORTED-{external_id}')[:58]
    candidate = base
    counter = 2
    queryset = ProductVariant.objects.all()
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)
    while queryset.filter(sku=candidate).exists():
        suffix = f'-{counter}'
        candidate = f'{base[:64 - len(suffix)]}{suffix}'
        counter += 1
    return candidate


def _normalize_remote_listing(provider: str, payload: dict) -> dict:
    offerings = payload.get('offerings') or []
    products = payload.get('products') or []
    first_product = products[0] if products and isinstance(products[0], dict) else {}
    first_offering = offerings[0] if offerings and isinstance(offerings[0], dict) else {}
    if not first_offering:
        nested_offerings = first_product.get('offerings') or []
        first_offering = nested_offerings[0] if nested_offerings and isinstance(nested_offerings[0], dict) else {}

    external_id = str(_first(payload, 'listing_id', 'id', 'product_id', 'external_listing_id'))
    sku = str(_first(payload, 'sku', default=_first(first_product, 'sku', default=external_id or 'IMPORTED')))
    title = str(_first(payload, 'title', 'name', default=f'{provider.title()} listing {external_id}'))
    description = str(_first(payload, 'description', 'body', 'short_description', default=''))
    price = _money(_first(payload, 'price', 'amount', default=_first(first_offering, 'price', default='0.00')))
    quantity = _quantity(_first(payload, 'quantity', 'stock', 'stock_quantity', default=_first(first_offering, 'quantity', default=0)))
    listing_url = str(_first(payload, 'url', 'listing_url', default=''))
    variant_id = str(_first(payload, 'variant_id', 'external_variant_id', default=_first(first_product, 'product_id', default='')))

    return {
        'external_id': external_id,
        'external_product_id': str(_first(payload, 'product_id', default=external_id)),
        'external_variant_id': variant_id,
        'title': title,
        'description': description,
        'sku': sku[:64],
        'price': price,
        'quantity': quantity,
        'listing_url': listing_url,
        'raw': payload,
    }


@transaction.atomic
def import_external_listing(channel_account: ChannelAccount, payload: dict) -> ExternalListing:
    normalized = _normalize_remote_listing(channel_account.provider, payload)
    if not normalized['external_id']:
        raise ValueError('Remote listing payload did not include a listing id.')

    listing = ExternalListing.objects.filter(
        provider=channel_account.provider,
        external_listing_id=normalized['external_id'],
    ).select_related('product', 'variant').first()

    if listing:
        product = listing.product
        variant = listing.variant or product.primary_variant
    else:
        product = Product.objects.create(
            name=normalized['title'],
            slug=_unique_slug(normalized['title'], normalized['external_id']),
            short_description=normalized['description'][:255],
            description=normalized['description'],
            product_type=Product.ProductType.EXTERNAL,
            default_source=channel_account.provider,
            is_active=True,
        )
        variant = ProductVariant.objects.create(
            product=product,
            title='Default',
            sku=_unique_sku(normalized['sku'], normalized['external_id']),
            price=normalized['price'],
            stock_quantity=normalized['quantity'],
            is_default=True,
            is_active=True,
        )

    if not variant:
        variant = ProductVariant.objects.create(
            product=product,
            title='Default',
            sku=_unique_sku(normalized['sku'], normalized['external_id']),
            price=normalized['price'],
            stock_quantity=normalized['quantity'],
            is_default=True,
            is_active=True,
        )

    if variant:
        variant.price = normalized['price']
        variant.stock_quantity = normalized['quantity']
        variant.last_sync_at = timezone.now()
        if normalized['sku']:
            variant.sku = _unique_sku(normalized['sku'], normalized['external_id'], exclude_pk=variant.pk)
        variant.save(update_fields=['price', 'stock_quantity', 'last_sync_at', 'sku'])

    product.name = normalized['title']
    product.short_description = normalized['description'][:255]
    product.description = normalized['description']
    product.product_type = Product.ProductType.EXTERNAL
    product.default_source = channel_account.provider
    product.save(update_fields=['name', 'short_description', 'description', 'product_type', 'default_source', 'updated_at'])

    listing, _ = ExternalListing.objects.update_or_create(
        provider=channel_account.provider,
        external_listing_id=normalized['external_id'],
        defaults={
            'channel_account': channel_account,
            'product': product,
            'variant': variant,
            'external_product_id': normalized['external_product_id'],
            'external_variant_id': normalized['external_variant_id'],
            'listing_url': normalized['listing_url'],
            'sync_state': ExternalListing.SyncState.SYNCED,
            'metadata': {
                **(listing.metadata if listing else {}),
                'last_import_payload': normalized['raw'],
            },
            'last_synced_at': timezone.now(),
        },
    )
    return listing


def import_channel_listings(channel_account: ChannelAccount, limit: int | None = None) -> list[ExternalListing]:
    connector = get_connector(channel_account)
    pull_listings = getattr(connector, 'pull_listings', None)
    if pull_listings is None:
        raise ValueError(f'{channel_account.get_provider_display()} does not support listing import.')
    payloads = pull_listings()
    if limit is not None:
        payloads = payloads[:limit]
    return [import_external_listing(channel_account, payload) for payload in payloads]


def sync_external_listing(listing: ExternalListing, *, push_inventory: bool = False) -> dict:
    connector = get_connector(listing.channel_account)
    result = connector.upsert_listing(listing)
    if push_inventory and listing.variant:
        result['inventory'] = connector.push_inventory(listing, listing.variant.stock_quantity)
    return result


def push_external_inventory(listing: ExternalListing, quantity: int | None = None) -> dict:
    connector = get_connector(listing.channel_account)
    if quantity is None:
        if not listing.variant:
            raise ValueError('Cannot push inventory for a listing without a linked variant.')
        quantity = listing.variant.stock_quantity
    return connector.push_inventory(listing, quantity)
