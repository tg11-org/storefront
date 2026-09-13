"""Fox Pay (foxpay.fyi) as a second way to pay, alongside Stripe.

Fox Pay is TG11's own payment service: the storefront creates a payment intent
over its API, sends the customer to Fox Pay's hosted checkout, and Fox Pay
reports the outcome back with a signed webhook. The shop never sees card
details - the same boundary Stripe gives us.

Two rules worth keeping in mind while reading:

* The **webhook is authoritative**, not the browser redirect. A customer who
  closes the tab still gets their order completed; a customer who forges a
  redirect gets nothing.
* Nothing here touches the Stripe path. If Fox Pay is unconfigured or down,
  checkout carries on exactly as it did before.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from orders.models import Order

logger = logging.getLogger(__name__)

TIMEOUT = 20
SUPPORTED_EVENTS = {"payment_intent.succeeded", "payment_intent.failed", "payment_intent.canceled"}


class FoxPayError(RuntimeError):
    """Something went wrong talking to Fox Pay; the message is safe to show."""


def _setting(name: str, default: str = "") -> str:
    return (getattr(settings, name, default) or "").strip()


def is_configured() -> bool:
    return bool(_setting("FOXPAY_API_KEY") and _setting("FOXPAY_API_BASE"))


def is_enabled() -> bool:
    """Offer it at checkout only when it is both switched on and usable."""
    return bool(getattr(settings, "FOXPAY_ENABLED", False)) and is_configured()


def _amount_to_minor_units(amount: Decimal) -> int:
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def create_payment_intent(order: Order, success_url: str, cancel_url: str) -> str:
    """Create the intent and return the hosted checkout URL to redirect to.

    The order number is both the idempotency key and the reference, so a
    double-submitted checkout reuses the same intent instead of charging twice.
    """
    if not is_configured():
        raise FoxPayError("Fox Pay is not configured for this store.")

    payload = {
        "amount": _amount_to_minor_units(order.grand_total),
        "currency": (order.pricing_snapshot or {}).get("currency", "") or _setting("STRIPE_CURRENCY", "USD").upper() or "USD",
        "description": f"Order {order.number}",
        "reference": order.number,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {"order_number": order.number, "source": "shop.tg11.org"},
        "customer": {
            "external_id": str(order.user_id or order.email),
            "email": order.email,
            "name": (order.shipping_address or {}).get("full_name", ""),
        },
    }
    tg11_uuid = _tg11_uuid_for(order)
    if tg11_uuid:
        # Only ever sent for an identity this shop actually authenticated.
        payload["customer"]["tg11_user_uuid"] = tg11_uuid

    try:
        response = requests.post(
            f"{_setting('FOXPAY_API_BASE').rstrip('/')}/api/v1/payment-intents/",
            json=payload,
            headers={
                "X-FoxPay-Key": _setting("FOXPAY_API_KEY"),
                "Idempotency-Key": f"order:{order.number}",
                "Content-Type": "application/json",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("Fox Pay is unreachable for order %s: %s", order.number, exc.__class__.__name__)
        raise FoxPayError("Fox Pay could not be reached. Try again, or pay by card.")

    if response.status_code not in (200, 201):
        detail = ""
        try:
            detail = (response.json().get("error") or {}).get("message", "")
        except ValueError:
            pass
        logger.warning("Fox Pay refused the intent for order %s (%s): %s", order.number, response.status_code, detail)
        raise FoxPayError(detail or "Fox Pay could not start that payment.")

    data = response.json()
    checkout_url = data.get("foxpay_checkout_url") or ""
    if not checkout_url:
        raise FoxPayError("Fox Pay did not return a checkout page.")

    _record(order, data, status="pending")
    return checkout_url


def _tg11_uuid_for(order: Order) -> str:
    """The customer's TG11 UUID, but only from a link this shop established."""
    if not order.user_id:
        return ""
    try:
        from tg11_auth.models import TG11IdentityLink

        link = TG11IdentityLink.objects.filter(user_id=order.user_id).first()
        return link.subject if link else ""
    except Exception:       # tg11_auth absent or mid-migration
        return ""


def _record(order: Order, intent: dict, status: str) -> None:
    from .models import PaymentRecord

    PaymentRecord.objects.update_or_create(
        order=order,
        stripe_checkout_session_id=f"foxpay:{intent.get('id', '')}",
        defaults={
            "user": order.user,
            "amount": order.grand_total,
            "currency": (intent.get("currency") or "USD").lower(),
            "status": PaymentRecord.Status.SUCCEEDED if status == "paid" else PaymentRecord.Status.PENDING,
            "metadata": {
                "provider": "foxpay",
                "foxpay_intent": intent.get("id", ""),
                "order_number": order.number,
                "status": intent.get("status", status),
            },
        },
    )


def sync_order(order: Order) -> Order:
    """Ask Fox Pay what happened, rather than trusting the redirect.

    The webhook is still authoritative; this exists so the success page can show
    the truth immediately instead of "pending payment" until the next delivery
    run. Everything it acts on comes from Fox Pay's own API over TLS, keyed by
    the intent id we stored when the payment started.
    """
    from .models import PaymentRecord

    if not is_configured():
        return order
    record = (PaymentRecord.objects.filter(order=order, metadata__provider="foxpay")
              .order_by("-created_at").first())
    intent_id = (record.metadata or {}).get("foxpay_intent") if record else ""
    if not intent_id:
        return order
    try:
        response = requests.get(
            f"{_setting('FOXPAY_API_BASE').rstrip('/')}/api/v1/payment-intents/{intent_id}/",
            headers={"X-FoxPay-Key": _setting("FOXPAY_API_KEY")},
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        return order
    if response.status_code != 200:
        return order
    intent = response.json()
    if intent.get("status") in ("succeeded", "paid", "completed"):
        return mark_paid(order, intent)
    return order


# --- webhooks -----------------------------------------------------------------

def signature_is_valid(body: bytes, supplied: str) -> bool:
    """Fox Pay signs the exact bytes with HMAC-SHA256 and the endpoint secret."""
    secret = _setting("FOXPAY_WEBHOOK_SECRET")
    if not secret or not supplied:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied.strip().lower())


def handle_event(body: bytes, supplied_signature: str) -> tuple[bool, str]:
    """(accepted, message). Never raises - a webhook receiver that 500s just
    gets retried forever."""
    if not signature_is_valid(body, supplied_signature):
        return False, "bad signature"
    try:
        event = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False, "unparseable body"

    event_type = event.get("type", "")
    intent = event.get("data") or {}
    if event_type not in SUPPORTED_EVENTS:
        return True, f"ignored {event_type}"

    order_number = (intent.get("metadata") or {}).get("order_number") or intent.get("reference") or ""
    if not order_number:
        return True, "no order reference"
    order = Order.objects.filter(number=order_number).first()
    if order is None:
        logger.warning("Fox Pay webhook for unknown order %s", order_number)
        return True, "unknown order"

    if event_type == "payment_intent.succeeded":
        mark_paid(order, intent)
        return True, f"order {order.number} paid"
    if event_type in ("payment_intent.failed", "payment_intent.canceled") and order.status != Order.Status.PAID:
        order.status = Order.Status.FAILED
        order.save(update_fields=["status", "updated_at"])
        return True, f"order {order.number} failed"
    return True, "no change"


@transaction.atomic
def mark_paid(order: Order, intent: dict) -> Order:
    """Complete the order exactly once, whatever order the webhook and the
    browser redirect arrive in."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    already_paid = order.status == Order.Status.PAID
    amount_ok = _amount_to_minor_units(order.grand_total) == intent.get("amount")
    if not amount_ok:
        logger.error("Fox Pay reported %s for order %s which totals %s - not completing it",
                     intent.get("amount"), order.number, order.grand_total)
        return order

    if not already_paid:
        order.status = Order.Status.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "paid_at", "updated_at"])
    _record(order, intent, status="paid")

    if already_paid:
        return order

    from cart.models import Cart
    from .services import decrement_internal_inventory, send_internal_fulfillment_email

    if order.cart_id:
        Cart.objects.filter(pk=order.cart_id).update(checked_out_at=timezone.now())
        order.cart.items.all().delete()
    try:
        _redeem_coupon(order)
        decrement_internal_inventory(order)
        send_internal_fulfillment_email(order)
        _queue_external_fulfillment(order)
        _send_confirmation(order)
    except Exception:
        logger.exception("Fox Pay: post-payment steps failed for order %s (the order is still paid)", order.number)
    return order


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


def _queue_external_fulfillment(order: Order) -> None:
    try:
        from connectors.services import queue_external_fulfillment_for_order
    except Exception:
        return
    queue_external_fulfillment_for_order(order)


def _send_confirmation(order: Order) -> None:
    try:
        from orders.services import send_order_confirmation_email
    except Exception:
        return
    send_order_confirmation_email(order)
