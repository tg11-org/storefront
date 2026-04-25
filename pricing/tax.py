from __future__ import annotations

from decimal import Decimal
import logging

import stripe
from django.conf import settings

from payments.services import StripeConfigurationError, get_stripe_client

from .services_math import amount_to_cents, cents_to_money

logger = logging.getLogger(__name__)


class TaxProviderError(RuntimeError):
    pass


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
        calculation = client.tax.Calculation.create(
            currency=settings.STRIPE_CURRENCY,
            customer_details={
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
            line_items=line_items,
            shipping_cost={
                'amount': amount_to_cents(shipping_total),
                'tax_behavior': settings.STRIPE_TAX_BEHAVIOR,
            },
            expand=['line_items'],
        )
    except stripe.error.StripeError as exc:
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
    return tax_total, snapshot
