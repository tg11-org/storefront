from __future__ import annotations

from decimal import Decimal
import json
import logging

import stripe
from django.conf import settings

from payments.services import StripeConfigurationError, get_stripe_client

from .services_math import amount_to_cents, cents_to_money

logger = logging.getLogger(__name__)


class TaxProviderError(RuntimeError):
    pass


def _stripe_payload(value):
    if hasattr(value, 'to_dict_recursive'):
        return _stripe_payload(value.to_dict_recursive())
    if hasattr(value, 'to_dict'):
        return _stripe_payload(value.to_dict())
    if isinstance(value, list):
        return [_stripe_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_stripe_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _stripe_payload(item) for key, item in value.items()}
    if isinstance(value, Decimal):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, '__dict__'):
        public_attrs = {
            key: item
            for key, item in vars(value).items()
            if not key.startswith('_')
        }
        if public_attrs:
            return _stripe_payload(public_attrs)
    return str(value)


def _json_safe_snapshot(snapshot: dict) -> dict:
    safe_snapshot = _stripe_payload(snapshot)
    try:
        json.dumps(safe_snapshot)
    except TypeError as exc:
        raise TaxProviderError(f'Stripe Tax returned a non-serializable snapshot: {exc}') from exc
    return safe_snapshot


def _ship_from_details() -> dict:
    address = {
        'line1': getattr(settings, 'SHIP_FROM_LINE1', ''),
        'line2': getattr(settings, 'SHIP_FROM_LINE2', ''),
        'city': getattr(settings, 'SHIP_FROM_CITY', ''),
        'state': getattr(settings, 'SHIP_FROM_STATE', ''),
        'postal_code': getattr(settings, 'SHIP_FROM_POSTAL_CODE', ''),
        'country': getattr(settings, 'SHIP_FROM_COUNTRY', 'US'),
    }
    address = {key: value for key, value in address.items() if value}
    if not address.get('country'):
        return {}
    return {'address': address}


def stripe_tax_calculation(items, subtotal_after_discount: Decimal, shipping_total: Decimal, shipping_address: dict) -> tuple[Decimal, dict]:
    if not settings.STRIPE_TAX_ENABLED:
        return Decimal('0.00'), {}
    try:
        client = get_stripe_client()
    except StripeConfigurationError as exc:
        raise TaxProviderError(str(exc)) from exc

    line_items = []
    remaining = subtotal_after_discount
    for index, item in enumerate(items):
        line_total = Decimal(str(item.variant.price)) * item.quantity
        amount = min(line_total, remaining)
        remaining -= amount
        if amount <= 0:
            continue
        line_items.append(
            {
                'amount': amount_to_cents(amount),
                'quantity': item.quantity,
                'reference': getattr(item.variant, 'sku', '') or f'item-{index}',
                'tax_behavior': settings.STRIPE_TAX_BEHAVIOR,
            }
        )

    if not line_items:
        return Decimal('0.00'), {}

    try:
        calculation_params = {
            'currency': settings.STRIPE_CURRENCY,
            'customer_details': {
                'address': {
                    'line1': shipping_address.get('line1', ''),
                    'line2': shipping_address.get('line2', ''),
                    'city': shipping_address.get('city', ''),
                    'state': shipping_address.get('state', ''),
                    'postal_code': shipping_address.get('postal_code', ''),
                    'country': shipping_address.get('country', 'US'),
                },
                'address_source': 'shipping',
            },
            'line_items': line_items,
            'shipping_cost': {
                'amount': amount_to_cents(shipping_total),
                'tax_behavior': settings.STRIPE_TAX_BEHAVIOR,
            },
            'expand': ['line_items'],
        }
        ship_from = _ship_from_details()
        if ship_from:
            calculation_params['ship_from_details'] = ship_from
        calculation = client.tax.Calculation.create(**calculation_params)
    except stripe.error.StripeError as exc:
        raise TaxProviderError(str(exc)) from exc
    except Exception as exc:
        raise TaxProviderError(str(exc)) from exc

    tax_total = cents_to_money(getattr(calculation, 'tax_amount_exclusive', 0) + getattr(calculation, 'tax_amount_inclusive', 0))
    snapshot = {
        'provider': 'stripe_tax',
        'calculation_id': getattr(calculation, 'id', ''),
        'amount_total': str(cents_to_money(getattr(calculation, 'amount_total', 0))),
        'tax_amount_exclusive': str(cents_to_money(getattr(calculation, 'tax_amount_exclusive', 0))),
        'tax_amount_inclusive': str(cents_to_money(getattr(calculation, 'tax_amount_inclusive', 0))),
        'tax_breakdown': getattr(calculation, 'tax_breakdown', []),
    }
    return tax_total, _json_safe_snapshot(snapshot)
