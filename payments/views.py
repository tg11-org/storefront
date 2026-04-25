import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from accounts.models import CustomUser
from orders.models import Order

from .services import (
    StripeConfigurationError,
    create_setup_session,
    finalize_order_from_checkout_session,
    get_stripe_client,
    is_configured_stripe_value,
    sync_saved_payment_methods,
)


@login_required
def add_payment_method(request):
    try:
        session = create_setup_session(
            request.user,
            request.build_absolute_uri(reverse('payments:setup_success')),
            request.build_absolute_uri(reverse('accounts:dashboard')),
        )
    except StripeConfigurationError as exc:
        messages.error(request, str(exc))
        return redirect('accounts:dashboard')
    except stripe.error.StripeError as exc:
        messages.error(request, f'Unable to start Stripe payment method setup: {exc}')
        return redirect('accounts:dashboard')
    return redirect(session.url, permanent=False)


@login_required
def setup_success(request):
    try:
        sync_saved_payment_methods(request.user)
    except stripe.error.StripeError as exc:
        messages.error(request, f'Unable to sync payment methods from Stripe: {exc}')
        return redirect('accounts:dashboard')
    messages.success(request, 'Payment method synced from Stripe.')
    return redirect('accounts:dashboard')


@csrf_exempt
def stripe_webhook(request):
    if not is_configured_stripe_value(settings.STRIPE_WEBHOOK_SECRET) or not is_configured_stripe_value(settings.STRIPE_SECRET_KEY):
        return HttpResponse(status=503)

    payload = request.body
    sig_header = request.headers.get('Stripe-Signature', '')
    client = get_stripe_client()
    try:
        event = client.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=settings.STRIPE_WEBHOOK_SECRET)
    except ValueError:
        return HttpResponseBadRequest('Invalid payload')
    except stripe.error.SignatureVerificationError:
        return HttpResponseBadRequest('Invalid signature')

    event_type = event.get('type', '')
    data = event.get('data', {}).get('object', {})

    if event_type == 'checkout.session.completed':
        if data.get('mode') == 'payment':
            session_id = data.get('id')
            if session_id:
                finalize_order_from_checkout_session(session_id)
        elif data.get('mode') == 'setup' and data.get('metadata', {}).get('user_id'):
            user = CustomUser.objects.filter(pk=data['metadata']['user_id']).first()
            if user:
                sync_saved_payment_methods(user)
    elif event_type == 'payment_intent.payment_failed':
        order_number = data.get('metadata', {}).get('order_number')
        if order_number:
            Order.objects.filter(number=order_number).update(status=Order.Status.FAILED)

    return HttpResponse(status=200)
