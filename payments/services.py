from __future__ import annotations

from decimal import Decimal
import logging

import stripe
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import F
from django.utils import timezone

from accounts.models import CustomerProfile
from cart.models import Cart
from catalog.models import ProductVariant
from connectors.services import queue_external_fulfillment_for_order
from orders.models import Order
from orders.services import send_order_confirmation_email
from pricing.models import Coupon, CouponRedemption

from .models import PaymentRecord, SavedPaymentMethodRef

logger = logging.getLogger(__name__)


class StripeConfigurationError(RuntimeError):
    pass


def is_configured_stripe_value(value: str | None) -> bool:
    return bool(value and 'replace_me' not in value)


def get_stripe_client() -> stripe:
    if not is_configured_stripe_value(settings.STRIPE_SECRET_KEY):
        raise StripeConfigurationError('Stripe secret key is not configured.')
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def _amount_to_cents(amount: Decimal) -> int:
    return int((amount * 100).quantize(Decimal('1')))


def ensure_stripe_customer(user):
    profile, _ = CustomerProfile.objects.get_or_create(user=user)
    if profile.stripe_customer_id:
        return profile.stripe_customer_id

    client = get_stripe_client()
    customer = client.Customer.create(
        email=user.email,
        name=f'{user.first_name} {user.last_name}'.strip() or user.email,
        metadata={'user_id': str(user.pk)},
    )
    profile.stripe_customer_id = customer.id
    profile.save(update_fields=['stripe_customer_id', 'updated_at'])
    return profile.stripe_customer_id


def create_checkout_session(order: Order, success_url: str, cancel_url: str):
    client = get_stripe_client()
    customer_id = ensure_stripe_customer(order.user) if order.user else None
    line_items = []
    use_summary_line = order.discount_total or order.shipping_total or order.tax_total
    if use_summary_line:
        line_items.append(
            {
                'price_data': {
                    'currency': settings.STRIPE_CURRENCY,
                    'product_data': {
                        'name': f'Order {order.number}',
                        'metadata': {'order_number': order.number},
                    },
                    'unit_amount': _amount_to_cents(order.grand_total),
                },
                'quantity': 1,
            }
        )
    else:
        for item in order.items.all():
            line_items.append(
                {
                    'price_data': {
                        'currency': settings.STRIPE_CURRENCY,
                        'product_data': {
                            'name': item.title,
                            'metadata': {'sku': item.sku, 'source': item.source, 'custom_request': item.custom_request[:500]},
                        },
                        'unit_amount': _amount_to_cents(item.unit_price),
                    },
                    'quantity': item.quantity,
                }
            )

    session = client.checkout.Session.create(
        mode='payment',
        customer=customer_id,
        client_reference_id=order.number,
        metadata={'order_number': order.number, 'user_id': str(order.user_id or ''), 'expected_total': str(order.grand_total)},
        line_items=line_items,
        success_url=success_url,
        cancel_url=cancel_url,
        saved_payment_method_options={'payment_method_save': 'enabled'},
        payment_intent_data={
            'metadata': {'order_number': order.number},
            'setup_future_usage': 'off_session',
        },
    )
    order.stripe_checkout_session_id = session.id
    order.save(update_fields=['stripe_checkout_session_id', 'updated_at'])
    PaymentRecord.objects.update_or_create(
        order=order,
        stripe_checkout_session_id=session.id,
        defaults={
            'user': order.user,
            'amount': order.grand_total,
            'currency': settings.STRIPE_CURRENCY,
            'status': PaymentRecord.Status.PENDING,
            'metadata': {'order_number': order.number},
        },
    )
    return session


def create_setup_session(user, success_url: str, cancel_url: str):
    client = get_stripe_client()
    customer_id = ensure_stripe_customer(user)
    return client.checkout.Session.create(
        mode='setup',
        customer=customer_id,
        currency=settings.STRIPE_CURRENCY,
        client_reference_id=str(user.pk),
        metadata={'user_id': str(user.pk), 'purpose': 'save_payment_method'},
        success_url=success_url,
        cancel_url=cancel_url,
    )


def sync_saved_payment_methods(user):
    profile = getattr(user, 'profile', None)
    if not profile or not profile.stripe_customer_id or not is_configured_stripe_value(settings.STRIPE_SECRET_KEY):
        return SavedPaymentMethodRef.objects.none()

    client = get_stripe_client()
    payment_methods = client.Customer.list_payment_methods(profile.stripe_customer_id, type='card')
    seen_ids = []
    for payment_method in payment_methods.auto_paging_iter():
        card = getattr(payment_method, 'card', None)
        ref, _ = SavedPaymentMethodRef.objects.update_or_create(
            stripe_payment_method_id=payment_method.id,
            defaults={
                'user': user,
                'stripe_customer_id': profile.stripe_customer_id,
                'brand': getattr(card, 'brand', '') or '',
                'last4': getattr(card, 'last4', '') or '',
                'exp_month': getattr(card, 'exp_month', None),
                'exp_year': getattr(card, 'exp_year', None),
                'allow_redisplay': getattr(payment_method, 'allow_redisplay', '') or '',
            },
        )
        seen_ids.append(ref.pk)
    if seen_ids:
        SavedPaymentMethodRef.objects.filter(user=user).exclude(pk__in=seen_ids).delete()
    return SavedPaymentMethodRef.objects.filter(user=user)


def _format_address(address: dict) -> str:
    lines = [
        address.get('full_name', ''),
        address.get('company_name', ''),
        address.get('line1', ''),
        address.get('line2', ''),
        ' '.join(part for part in [address.get('city', ''), address.get('state', ''), address.get('postal_code', '')] if part),
        address.get('country', ''),
        address.get('phone_number', ''),
    ]
    return '\n'.join(line for line in lines if line)


def _internal_order_items(order: Order):
    return [
        item for item in order.items.select_related('variant')
        if item.source == Order.Source.INTERNAL and item.variant_id
    ]


def decrement_internal_inventory(order: Order) -> None:
    for item in _internal_order_items(order):
        ProductVariant.objects.filter(pk=item.variant_id, stock_quantity__gte=item.quantity).update(stock_quantity=F('stock_quantity') - item.quantity)


def send_internal_fulfillment_email(order: Order) -> None:
    if not settings.FULFILLMENT_EMAIL_RECIPIENTS:
        return
    items = _internal_order_items(order)
    if not items:
        return
    item_lines = '\n'.join(
        f'- {item.quantity} x {item.title} ({item.sku or "no sku"}) at ${item.unit_price}'
        + (f'\n  Custom request: {item.custom_request}' if item.custom_request else '')
        for item in items
    )
    message = (
        f'Hey, you have an order to fulfill.\n\n'
        f'Order: {order.number}\n'
        f'Customer email: {order.email}\n'
        f'Paid total: ${order.grand_total}\n\n'
        f'Discounts: ${order.discount_total}\n'
        f'Shipping: ${order.shipping_total}\n\n'
        f'Items:\n{item_lines}\n\n'
        f'Ship to:\n{_format_address(order.shipping_address)}\n\n'
        f'Notes:\n{order.notes or "None"}\n'
    )
    send_mail(
        subject=f'TG11 Shop order to fulfill: {order.number}',
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=settings.FULFILLMENT_EMAIL_RECIPIENTS,
        fail_silently=True,
    )


def finalize_order_from_checkout_session(session_id: str, order_number: str | None = None):
    if not is_configured_stripe_value(settings.STRIPE_SECRET_KEY):
        return None
    client = get_stripe_client()
    session = client.checkout.Session.retrieve(session_id)
    metadata = getattr(session, 'metadata', None) or {}
    order_number = order_number or metadata.get('order_number') or getattr(session, 'client_reference_id', '')
    if not order_number:
        return None
    order = Order.objects.prefetch_related('items').filter(number=order_number).first()
    if not order:
        return None

    payment_status = getattr(session, 'payment_status', '')
    intent_id = getattr(session, 'payment_intent', '') or ''
    if payment_status == 'paid':
        was_paid = order.status == Order.Status.PAID
        order.status = Order.Status.PAID
        order.paid_at = timezone.now()
        order.stripe_payment_intent_id = intent_id
        order.save(update_fields=['status', 'paid_at', 'stripe_payment_intent_id', 'updated_at'])
        PaymentRecord.objects.update_or_create(
            order=order,
            stripe_checkout_session_id=session.id,
            defaults={
                'user': order.user,
                'amount': order.grand_total,
                'currency': settings.STRIPE_CURRENCY,
                'status': PaymentRecord.Status.SUCCEEDED,
                'stripe_payment_intent_id': intent_id,
                'metadata': {'order_number': order.number},
            },
        )
        if order.user and not was_paid:
            try:
                sync_saved_payment_methods(order.user)
            except stripe.error.StripeError:
                logger.exception('Unable to sync saved payment methods for order %s.', order.number)
        if order.cart_id and not was_paid:
            Cart.objects.filter(pk=order.cart_id).update(checked_out_at=timezone.now())
            order.cart.items.all().delete()
        if not was_paid:
            try:
                if order.coupon_code:
                    coupon = Coupon.objects.filter(code=order.coupon_code).first()
                    if coupon:
                        CouponRedemption.objects.get_or_create(
                            coupon=coupon,
                            order=order,
                            defaults={'user': order.user, 'email': order.email},
                        )
                        Coupon.objects.filter(pk=coupon.pk).update(usage_count=F('usage_count') + 1)
                decrement_internal_inventory(order)
                send_internal_fulfillment_email(order)
                queue_external_fulfillment_for_order(order)
            except Exception:
                logger.exception('Unable to complete post-payment fulfillment side effects for order %s.', order.number)
            if order.user_id:
                try:
                    send_order_confirmation_email(order)
                except Exception:
                    logger.exception('Unable to send order confirmation email for order %s.', order.number)
    return order
