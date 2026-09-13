"""PayPal Checkout (Orders v2) as a third way to pay.

The flow is deliberately server-side: the shop creates an order at PayPal, sends
the buyer to PayPal's approval page, and captures the money itself when PayPal
sends the buyer back. No card details, no client-side SDK, nothing the browser
says is trusted - the capture call and the webhook are what complete an order.

Configuration (all from the environment, nothing hard-coded):

    PAYPAL_ENV            sandbox | live
    PAYPAL_CLIENT_ID
    PAYPAL_CLIENT_SECRET
    PAYPAL_WEBHOOK_ID     the id PayPal shows for the webhook you register
    PAYPAL_ENABLED        true to offer it at checkout
"""
from __future__ import annotations

import logging
import time

import requests
from django.conf import settings

from orders.models import Order

from .completion import amount_to_minor_units, complete_order, record_payment

logger = logging.getLogger(__name__)

TIMEOUT = 20
LIVE = "https://api-m.paypal.com"
SANDBOX = "https://api-m.sandbox.paypal.com"
_token_cache: dict = {"value": "", "expires": 0.0}


class PayPalError(RuntimeError):
    """Safe to show the customer."""


def _setting(name: str, default: str = "") -> str:
    return (getattr(settings, name, default) or "").strip()


def api_base() -> str:
    return SANDBOX if _setting("PAYPAL_ENV", "sandbox").lower() != "live" else LIVE


def is_configured() -> bool:
    return bool(_setting("PAYPAL_CLIENT_ID") and _setting("PAYPAL_CLIENT_SECRET"))


def is_enabled() -> bool:
    return bool(getattr(settings, "PAYPAL_ENABLED", False)) and is_configured()


def access_token(force: bool = False) -> str:
    """Client-credentials token, cached until shortly before it expires."""
    if not force and _token_cache["value"] and time.time() < _token_cache["expires"]:
        return _token_cache["value"]
    if not is_configured():
        raise PayPalError("PayPal is not configured for this store.")
    try:
        response = requests.post(
            f"{api_base()}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(_setting("PAYPAL_CLIENT_ID"), _setting("PAYPAL_CLIENT_SECRET")),
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PayPalError(f"PayPal could not be reached ({exc.__class__.__name__}).")
    if response.status_code != 200:
        logger.warning("PayPal token request failed (%s)", response.status_code)
        raise PayPalError("PayPal rejected this store's credentials.")
    data = response.json()
    _token_cache["value"] = data.get("access_token", "")
    _token_cache["expires"] = time.time() + max(60, int(data.get("expires_in", 600)) - 60)
    return _token_cache["value"]


def _call(method: str, path: str, *, json_body: dict | None = None, retry: bool = True):
    try:
        response = requests.request(
            method,
            f"{api_base()}{path}",
            json=json_body,
            headers={"Authorization": f"Bearer {access_token()}", "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PayPalError(f"PayPal could not be reached ({exc.__class__.__name__}).")
    if response.status_code == 401 and retry:
        access_token(force=True)                 # the token expired early
        return _call(method, path, json_body=json_body, retry=False)
    return response


def create_order(order: Order, return_url: str, cancel_url: str) -> str:
    """Create the PayPal order and return the URL to send the buyer to."""
    currency = (_setting("STRIPE_CURRENCY", "USD") or "USD").upper()
    body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": order.number,
            "custom_id": order.number,
            "invoice_id": order.number,
            "description": f"Order {order.number}"[:127],
            "amount": {"currency_code": currency, "value": f"{order.grand_total:.2f}"},
        }],
        "application_context": {
            "brand_name": _site_name(),
            "user_action": "PAY_NOW",
            "shipping_preference": "NO_SHIPPING",   # the shop already collected it
            "return_url": return_url,
            "cancel_url": cancel_url,
        },
    }
    response = _call("POST", "/v2/checkout/orders", json_body=body)
    if response.status_code not in (200, 201):
        logger.warning("PayPal refused the order for %s (%s)", order.number, response.status_code)
        raise PayPalError("PayPal could not start that payment.")
    data = response.json()
    record_payment(order, provider="paypal", reference=data.get("id", ""), currency=currency, paid=False, raw=data)
    for link in data.get("links", []):
        if link.get("rel") in ("approve", "payer-action"):
            return link["href"]
    raise PayPalError("PayPal did not return an approval link.")


def _site_name() -> str:
    try:
        from catalog.models import StoreSettings

        return StoreSettings.current().name
    except Exception:
        return "TG11 Shop"


def capture_order(order: Order, paypal_order_id: str) -> Order:
    """Take the money and complete the order. Safe to call twice."""
    response = _call("POST", f"/v2/checkout/orders/{paypal_order_id}/capture", json_body={})
    data = {}
    try:
        data = response.json()
    except ValueError:
        pass
    if response.status_code == 422 and _already_captured(data):
        return sync_order(order, paypal_order_id)
    if response.status_code not in (200, 201):
        logger.warning("PayPal capture failed for order %s (%s)", order.number, response.status_code)
        raise PayPalError("PayPal could not complete that payment.")
    return _complete_from(order, data)


def _already_captured(data: dict) -> bool:
    return any(d.get("issue") == "ORDER_ALREADY_CAPTURED" for d in (data.get("details") or []))


def sync_order(order: Order, paypal_order_id: str) -> Order:
    """Ask PayPal what the truth is, rather than trusting the redirect."""
    response = _call("GET", f"/v2/checkout/orders/{paypal_order_id}")
    if response.status_code != 200:
        return order
    return _complete_from(order, response.json())


def _complete_from(order: Order, data: dict) -> Order:
    if str(data.get("status", "")).upper() != "COMPLETED":
        record_payment(order, provider="paypal", reference=data.get("id", ""), paid=False, raw=data)
        return order
    unit = (data.get("purchase_units") or [{}])[0]
    captures = ((unit.get("payments") or {}).get("captures") or [{}])
    amount = captures[0].get("amount") or unit.get("amount") or {}
    minor = None
    if amount.get("value"):
        minor = amount_to_minor_units(amount["value"])
    return complete_order(order, provider="paypal", reference=data.get("id", ""),
                          amount_minor=minor, currency=amount.get("currency_code", "USD"), raw=data)


def order_id_for(order: Order) -> str:
    from .models import PaymentRecord

    record = (PaymentRecord.objects.filter(order=order, metadata__provider="paypal")
              .order_by("-created_at").first())
    return (record.metadata or {}).get("paypal_reference", "") if record else ""


# --- webhooks -----------------------------------------------------------------

def verify_webhook(headers, body: bytes) -> bool:
    """PayPal verifies its own signatures: we hand the headers back to them.

    Without PAYPAL_WEBHOOK_ID there is no way to check anything, so the answer
    is no - an unverifiable webhook is refused rather than trusted.
    """
    webhook_id = _setting("PAYPAL_WEBHOOK_ID")
    if not webhook_id:
        return False
    required = ("Paypal-Transmission-Id", "Paypal-Transmission-Time", "Paypal-Cert-Url",
                "Paypal-Auth-Algo", "Paypal-Transmission-Sig")
    if any(not headers.get(h) for h in required):
        return False
    import json as _json

    try:
        event = _json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False
    payload = {
        "transmission_id": headers.get("Paypal-Transmission-Id"),
        "transmission_time": headers.get("Paypal-Transmission-Time"),
        "cert_url": headers.get("Paypal-Cert-Url"),
        "auth_algo": headers.get("Paypal-Auth-Algo"),
        "transmission_sig": headers.get("Paypal-Transmission-Sig"),
        "webhook_id": webhook_id,
        "webhook_event": event,
    }
    response = _call("POST", "/v1/notifications/verify-webhook-signature", json_body=payload)
    if response.status_code != 200:
        return False
    return response.json().get("verification_status") == "SUCCESS"


def handle_event(headers, body: bytes) -> tuple[bool, str]:
    import json as _json

    if not verify_webhook(headers, body):
        return False, "unverified webhook"
    event = _json.loads(body.decode("utf-8"))
    event_type = event.get("event_type", "")
    resource = event.get("resource") or {}
    if event_type not in ("CHECKOUT.ORDER.APPROVED", "PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.DENIED"):
        return True, f"ignored {event_type}"

    order_number = (resource.get("custom_id") or resource.get("invoice_id")
                    or ((resource.get("purchase_units") or [{}])[0].get("custom_id") if resource.get("purchase_units") else ""))
    order = Order.objects.filter(number=order_number).first() if order_number else None
    if order is None:
        return True, "unknown order"

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        amount = resource.get("amount") or {}
        complete_order(order, provider="paypal", reference=resource.get("id", ""),
                       amount_minor=amount_to_minor_units(amount.get("value", "0")),
                       currency=amount.get("currency_code", "USD"), raw=resource)
        return True, f"order {order.number} paid"
    if event_type == "CHECKOUT.ORDER.APPROVED" and order.status != Order.Status.PAID:
        # approved is not paid: capture it ourselves, then it is
        try:
            capture_order(order, resource.get("id", ""))
        except PayPalError as exc:
            return True, f"approved but capture failed: {exc}"
        return True, f"order {order.number} captured"
    if event_type == "PAYMENT.CAPTURE.DENIED" and order.status != Order.Status.PAID:
        order.status = Order.Status.FAILED
        order.save(update_fields=["status", "updated_at"])
        return True, f"order {order.number} denied"
    return True, "no change"
