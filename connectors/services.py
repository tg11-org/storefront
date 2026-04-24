from __future__ import annotations

from collections import defaultdict

from django.utils import timezone

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
