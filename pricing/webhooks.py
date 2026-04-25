from __future__ import annotations

import hashlib
import hmac
import json
import re

from django.conf import settings

from orders.models import FulfillmentUpdate, Order

from .models import ShippingWebhookEvent


ORDER_NUMBER_RE = re.compile(r'\b[A-Z0-9]{2,12}-[A-F0-9]{10}\b')


def _walk(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)
    elif value is not None:
        yield str(value)


def verify_shared_secret(request, secret: str) -> bool:
    if not secret:
        return True
    candidates = [
        request.headers.get('X-Webhook-Secret', ''),
        request.headers.get('X-WeSupply-Webhook-Secret', ''),
        request.headers.get('X-EasyPost-Webhook-Secret', ''),
        request.headers.get('X-Shippo-Webhook-Secret', ''),
        request.GET.get('secret', ''),
    ]
    if any(hmac.compare_digest(candidate, secret) for candidate in candidates if candidate):
        return True

    body = request.body
    digest_hex = hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
    digest_sha = f'sha256={digest_hex}'
    signature_headers = [
        request.headers.get('X-Hook-Signature', ''),
        request.headers.get('X-Webhook-Signature', ''),
        request.headers.get('X-EasyPost-Hmac-Signature', ''),
        request.headers.get('X-Shippo-Hmac-Signature', ''),
    ]
    return any(hmac.compare_digest(signature, digest_hex) or hmac.compare_digest(signature, digest_sha) for signature in signature_headers if signature)


def parse_payload(raw_body: bytes) -> dict:
    if not raw_body:
        return {}
    return json.loads(raw_body.decode('utf-8'))


def event_identity(provider: str, payload: dict) -> tuple[str, str]:
    event_id = str(payload.get('id') or payload.get('object_id') or payload.get('event') or '')
    event_type = str(payload.get('description') or payload.get('event_type') or payload.get('type') or payload.get('object') or '')
    return event_id, event_type


def find_order_for_shipping_payload(payload: dict) -> Order | None:
    for value in _walk(payload):
        match = ORDER_NUMBER_RE.search(value)
        if match:
            order = Order.objects.filter(number=match.group(0)).first()
            if order:
                return order

    values = set(_walk(payload))
    for order in Order.objects.exclude(shipping_rate_snapshot={}):
        snapshot = order.shipping_rate_snapshot or {}
        identifiers = {snapshot.get('external_rate_id', ''), snapshot.get('external_shipment_id', '')}
        if identifiers & values:
            return order
    return None


def extract_tracking(payload: dict) -> tuple[str, str, str]:
    tracking_number = ''
    carrier = ''
    status = ''
    for key, value in _flatten_items(payload):
        key_lower = key.lower()
        if not tracking_number and key_lower in {'tracking_code', 'tracking_number', 'tracking'}:
            tracking_number = str(value)
        if not carrier and key_lower in {'carrier', 'provider'}:
            carrier = str(value).lower()
        if not status and key_lower in {'status', 'tracking_status'}:
            status = str(value).lower()
    return tracking_number, carrier, status


def _flatten_items(value, prefix=''):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _flatten_items(item, str(key))
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_items(item, prefix)
    else:
        yield prefix, value


def status_for_tracking(provider_status: str) -> str:
    if provider_status in {'delivered', 'success'}:
        return Order.FulfillmentStatus.DELIVERED
    if provider_status in {'in_transit', 'transit', 'out_for_delivery', 'pre_transit', 'shipped'}:
        return Order.FulfillmentStatus.SHIPPED
    return Order.FulfillmentStatus.IN_PROGRESS


def tracking_url(provider: str, tracking_number: str) -> str:
    if provider == 'easypost' and settings.EASYPOST_TRACKING_URL:
        return f'{settings.EASYPOST_TRACKING_URL.rstrip("/")}/{tracking_number}'
    return ''


def record_shipping_webhook(provider: str, payload: dict) -> ShippingWebhookEvent:
    event_id, event_type = event_identity(provider, payload)
    order = find_order_for_shipping_payload(payload)
    tracking_number, carrier, provider_status = extract_tracking(payload)
    processed = False
    message = ''

    if order and tracking_number:
        FulfillmentUpdate.objects.create(
            order=order,
            status=status_for_tracking(provider_status),
            tracking_number=tracking_number,
            carrier=carrier if carrier in {'ups', 'fedex', 'usps', 'dhl'} else 'other',
            tracking_url=tracking_url(provider, tracking_number),
            notes=f'{provider} webhook: {provider_status or event_type}',
        )
        processed = True
        message = f'Updated {order.number} tracking.'
    elif order:
        processed = True
        message = f'Matched {order.number}; no tracking number in payload.'
    else:
        message = 'No matching order found.'

    return ShippingWebhookEvent.objects.create(
        provider=provider,
        event_id=event_id,
        event_type=event_type,
        order=order,
        payload=payload,
        processed=processed,
        message=message,
    )
