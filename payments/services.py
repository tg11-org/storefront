from __future__ import annotations

from decimal import Decimal

import stripe
from django.conf import settings
from django.utils import timezone

from accounts.models import CustomerProfile
from cart.models import Cart
from connectors.services import queue_external_fulfillment_for_order
from orders.models import Order

from .models import PaymentRecord, SavedPaymentMethodRef


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
    for item in order.items.all():
        line_items.append(
            {
                'price_data': {
                    'currency': settings.STRIPE_CURRENCY,
                    'product_data': {
                        'name': item.title,
                        'metadata': {'sku': item.sku, 'source': item.source},
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
        metadata={'order_number': order.number, 'user_id': str(order.user_id or '')},
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


def finalize_order_from_checkout_session(session_id: str):
    if not is_configured_stripe_value(settings.STRIPE_SECRET_KEY):
        return None
    client = get_stripe_client()
    session = client.checkout.Session.retrieve(session_id)
    order_number = session.metadata.get('order_number') or session.client_reference_id
    if not order_number:
        return None
    order = Order.objects.prefetch_related('items').filter(number=order_number).first()
    if not order:
        return None

    payment_status = getattr(session, 'payment_status', '')
    intent_id = getattr(session, 'payment_intent', '') or ''
    if payment_status == 'paid':
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
        if order.user:
            sync_saved_payment_methods(order.user)
        if order.cart_id:
            Cart.objects.filter(pk=order.cart_id).update(checked_out_at=timezone.now())
            order.cart.items.all().delete()
        queue_external_fulfillment_for_order(order)
    return order
