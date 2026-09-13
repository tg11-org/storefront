"""Completing an order, once - whoever says it was paid.

Stripe, Fox Pay and PayPal all end at the same place: this order is paid, so
clear the cart, redeem the coupon, take the stock, tell fulfilment and email the
customer. That has to happen exactly once even when a webhook and a browser
redirect race each other, so it lives here rather than three times over.

The Stripe path predates this and still has its own copy; it is left alone
deliberately - it works, and rewriting a live checkout to share code is not
worth the risk today.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from orders.models import Order

logger = logging.getLogger(__name__)


def amount_to_minor_units(amount) -> int:
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


@transaction.atomic
def complete_order(order: Order, *, provider: str, reference: str, amount_minor: int,
                   currency: str = "USD", raw: dict | None = None) -> Order:
    """Mark an order paid and run the side effects once.

    `amount_minor` is checked against the order total first: a webhook that
    claims an order was paid for less than it costs completes nothing.
    """
    order = Order.objects.select_for_update().get(pk=order.pk)
    expected = amount_to_minor_units(order.grand_total)
    if amount_minor is not None and amount_minor != expected:
        logger.error("%s reported %s for order %s which totals %s - not completing it",
                     provider, amount_minor, order.number, expected)
        return order

    already_paid = order.status == Order.Status.PAID
    if not already_paid:
        order.status = Order.Status.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "paid_at", "updated_at"])
    record_payment(order, provider=provider, reference=reference, currency=currency, paid=True, raw=raw)

    if already_paid:
        return order

    from cart.models import Cart

    if order.cart_id:
        Cart.objects.filter(pk=order.cart_id).update(checked_out_at=timezone.now())
        order.cart.items.all().delete()
    try:
        _redeem_coupon(order)
        _take_stock_and_notify(order)
    except Exception:
        logger.exception("%s: post-payment steps failed for order %s (the order is still paid)", provider, order.number)
    return order


def record_payment(order: Order, *, provider: str, reference: str, currency: str = "USD",
                   paid: bool = False, raw: dict | None = None) -> None:
    from .models import PaymentRecord

    PaymentRecord.objects.update_or_create(
        order=order,
        stripe_checkout_session_id=f"{provider}:{reference}",
        defaults={
            "user": order.user,
            "amount": order.grand_total,
            "currency": (currency or "USD").lower(),
            "status": PaymentRecord.Status.SUCCEEDED if paid else PaymentRecord.Status.PENDING,
            "metadata": {
                "provider": provider,
                f"{provider}_reference": reference,
                "order_number": order.number,
                **({"status": raw.get("status", "")} if isinstance(raw, dict) else {}),
            },
        },
    )


def _redeem_coupon(order: Order) -> None:
    if not order.coupon_code:
        return
    from django.db.models import F

    from pricing.models import Coupon, CouponRedemption

    coupon = Coupon.objects.filter(code=order.coupon_code).first()
    if coupon:
        CouponRedemption.objects.get_or_create(coupon=coupon, order=order,
                                               defaults={"user": order.user, "email": order.email})
        Coupon.objects.filter(pk=coupon.pk).update(usage_count=F("usage_count") + 1)


def _take_stock_and_notify(order: Order) -> None:
    from .services import decrement_internal_inventory, send_internal_fulfillment_email

    decrement_internal_inventory(order)
    send_internal_fulfillment_email(order)
    try:
        from connectors.services import queue_external_fulfillment_for_order

        queue_external_fulfillment_for_order(order)
    except Exception:
        logger.exception("external fulfilment could not be queued for order %s", order.number)
    try:
        from orders.services import send_order_confirmation_email

        send_order_confirmation_email(order)
    except Exception:
        logger.exception("confirmation email could not be sent for order %s", order.number)
