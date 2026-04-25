import stripe
import logging
import hashlib
import json
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import FormView, TemplateView

from accounts.models import Address
from cart.views import get_or_create_cart
from catalog.models import StoreSettings
from connectors.models import ExternalListing
from orders.models import Order, OrderItem
from payments.services import StripeConfigurationError, create_checkout_session, finalize_order_from_checkout_session
from pricing.services import calculate_cart_totals, quote_shipping_methods, shipping_quote_from_snapshot

from .forms import CheckoutForm

logger = logging.getLogger(__name__)


class CheckoutView(LoginRequiredMixin, FormView):
    template_name = 'checkout/checkout.html'
    form_class = CheckoutForm

    def dispatch(self, request, *args, **kwargs):
        self.cart = get_or_create_cart(request)
        if not self.cart or not self.cart.items.exists():
            messages.info(request, 'Your cart is empty.')
            return redirect('cart:detail')
        unavailable_items = [
            item for item in self.cart.items.select_related('product', 'variant')
            if item.quantity > item.variant.stock_quantity
            or item.quantity > item.variant.effective_max_order_quantity
        ]
        if unavailable_items:
            messages.error(request, 'One or more cart items exceed stock or per-order quantity limits. Update your cart before checkout.')
            return redirect('cart:detail')
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        initial['coupon_code'] = self.cart.applied_coupon_code
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cart'] = self.cart
        context['totals'] = calculate_cart_totals(
            self.cart,
            self.request.user,
            coupon_code=self.cart.applied_coupon_code,
        )
        return context

    def form_valid(self, form):
        preview_only = self.request.POST.get('confirm_checkout') != '1'
        shipping_address = self._resolve_shipping_address(form, save_new=not preview_only)
        billing_address = self._resolve_billing_address(form, shipping_address, save_new=not preview_only)
        if self.request.POST.get('confirm_checkout') != '1':
            quotes = quote_shipping_methods(shipping_address.as_dict(), self.cart)
            if not quotes:
                form.add_error(None, 'No shipping methods are available for that address yet. Check shipping settings or try again shortly.')
                return self.form_invalid(form)
            self._store_quote_preview(shipping_address.as_dict(), quotes)
            context = self.get_context_data(form=form)
            context['shipping_quotes'] = quotes
            context['quote_preview_ready'] = True
            context['shipping_signature'] = self._cart_address_signature(shipping_address.as_dict())
            return self.render_to_response(context)
        try:
            order = self._build_order(form, shipping_address, billing_address)
        except ValueError:
            return self._form_invalid_with_quote_preview(form)
        try:
            session = create_checkout_session(
                order,
                self.request.build_absolute_uri(reverse('checkout:success')) + f'?order={order.number}&session_id={{CHECKOUT_SESSION_ID}}',
                self.request.build_absolute_uri(reverse('checkout:cancel')) + f'?order={order.number}',
            )
        except (StripeConfigurationError, stripe.error.StripeError) as exc:
            order.status = Order.Status.FAILED
            order.save(update_fields=['status', 'updated_at'])
            form.add_error(None, str(exc))
            return self._form_invalid_with_quote_preview(form)
        return redirect(session.url, permanent=False)

    def _form_invalid_with_quote_preview(self, form):
        context = self.get_context_data(form=form)
        quote_preview = self.request.session.get('checkout_quote_preview') or {}
        if quote_preview.get('quotes'):
            context['shipping_quotes'] = [shipping_quote_from_snapshot(quote) for quote in quote_preview['quotes']]
            context['quote_preview_ready'] = True
            context['shipping_signature'] = quote_preview.get('signature', '')
        return self.render_to_response(context)

    def _cart_address_signature(self, shipping_address: dict) -> str:
        cart_bits = [
            {
                'variant': item.variant_id,
                'quantity': item.quantity,
                'custom_request': item.custom_request,
                'updated_at': item.updated_at.isoformat(),
            }
            for item in self.cart.items.order_by('pk')
        ]
        payload = {'cart': cart_bits, 'shipping_address': shipping_address}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode('utf-8')).hexdigest()

    def _store_quote_preview(self, shipping_address: dict, quotes) -> None:
        self.request.session['checkout_quote_preview'] = {
            'signature': self._cart_address_signature(shipping_address),
            'quotes': [quote.snapshot() for quote in quotes],
        }
        self.request.session.modified = True

    def _resolve_shipping_address(self, form, save_new=True):
        address = form.cleaned_data['shipping_address']
        if address:
            return address
        address = Address(
            user=self.request.user,
            address_type=Address.AddressType.SHIPPING,
            label='Checkout shipping',
            full_name=form.cleaned_data['full_name'],
            company_name=form.cleaned_data['company_name'],
            line1=form.cleaned_data['line1'],
            line2=form.cleaned_data['line2'],
            city=form.cleaned_data['city'],
            state=form.cleaned_data['state'],
            postal_code=form.cleaned_data['postal_code'],
            country=form.cleaned_data['country'],
            phone_number=form.cleaned_data['phone_number'],
            is_default=form.cleaned_data['save_address'],
        )
        if not save_new:
            return address
        address.save()
        if address.is_default:
            self.request.user.addresses.filter(address_type=Address.AddressType.SHIPPING).exclude(pk=address.pk).update(is_default=False)
        return address

    def _resolve_billing_address(self, form, shipping_address, save_new=True):
        if form.cleaned_data['same_as_shipping']:
            return shipping_address
        address = form.cleaned_data['billing_address']
        if address:
            return address
        address = Address(
            user=self.request.user,
            address_type=Address.AddressType.BILLING,
            label='Checkout billing',
            full_name=form.cleaned_data['billing_full_name'],
            line1=form.cleaned_data['billing_line1'],
            line2=form.cleaned_data['billing_line2'],
            city=form.cleaned_data['billing_city'],
            state=form.cleaned_data['billing_state'],
            postal_code=form.cleaned_data['billing_postal_code'],
            country=form.cleaned_data['billing_country'],
        )
        if save_new:
            address.save()
        return address

    def _build_order(self, form, shipping_address, billing_address):
        source = Order.Source.INTERNAL
        cart_items = self.cart.items.select_related('product', 'variant')
        if any(item.product.default_source == 'etsy' for item in cart_items):
            source = Order.Source.ETSY
        elif any(item.product.default_source == 'popcustoms' for item in cart_items):
            source = Order.Source.POPCUSTOMS

        coupon_code = form.cleaned_data.get('coupon_code') or self.cart.applied_coupon_code
        selected_quote_id = form.cleaned_data.get('shipping_rate_rule')
        quote_preview = self.request.session.get('checkout_quote_preview') or {}
        if quote_preview.get('signature') != self._cart_address_signature(shipping_address.as_dict()):
            form.add_error(None, 'Shipping quotes changed. Review shipping again before payment.')
            raise ValueError('Stale shipping quote')
        if quote_preview.get('quotes') and selected_quote_id not in {quote['quote_id'] for quote in quote_preview['quotes']}:
            form.add_error('shipping_rate_rule', 'Choose a shipping method.')
            raise ValueError('Missing shipping quote')
        totals = calculate_cart_totals(
            self.cart,
            self.request.user,
            shipping_address=shipping_address.as_dict(),
            coupon_code=coupon_code,
            shipping_quote_id=selected_quote_id,
            shipping_quotes=[shipping_quote_from_snapshot(quote) for quote in quote_preview.get('quotes', [])],
        )
        if coupon_code and not totals.coupon:
            form.add_error('coupon_code', 'Coupon could not be applied.')
            raise ValueError('Invalid coupon')
        order = Order.objects.create(
            user=self.request.user,
            cart=self.cart,
            email=self.request.user.email,
            status=Order.Status.PENDING_PAYMENT,
            source=source,
            sync_state=Order.SyncState.PENDING if source != Order.Source.INTERNAL else Order.SyncState.NOT_APPLICABLE,
            shipping_address=shipping_address.as_dict(),
            billing_address=billing_address.as_dict(),
            subtotal=totals.subtotal,
            discount_total=totals.discount_total,
            tax_total=totals.tax_total,
            shipping_total=totals.shipping_total,
            grand_total=totals.grand_total,
            coupon_code=totals.coupon.code if totals.coupon else '',
            discount_snapshot=[
                {'kind': rule.kind, 'code': rule.code, 'label': rule.label, 'amount': str(rule.amount), 'metadata': rule.metadata}
                for rule in totals.applied_rules
            ],
            shipping_method=totals.shipping_quote.method_name if totals.shipping_quote else '',
            shipping_rate_snapshot=totals.shipping_quote.snapshot() if totals.shipping_quote else {},
            tax_snapshot=totals.tax_snapshot,
            pricing_snapshot=totals.audit_snapshot(),
            notes=form.cleaned_data['notes'],
        )
        OrderItem.objects.bulk_create([
            OrderItem(
                order=order,
                product=cart_item.product,
                variant=cart_item.variant,
                title=cart_item.product.name,
                sku=cart_item.variant.sku,
                quantity=cart_item.quantity,
                unit_price=cart_item.variant.price,
                source=cart_item.product.default_source,
                external_listing_id=self._external_listing_id(cart_item),
                custom_request=cart_item.custom_request,
            )
            for cart_item in cart_items
        ])
        if totals.coupon:
            self.cart.applied_coupon_code = totals.coupon.code
            self.cart.save(update_fields=['applied_coupon_code', 'updated_at'])
        return order

    def _external_listing_id(self, cart_item):
        if cart_item.product.default_source == Order.Source.INTERNAL:
            return ''
        listing = ExternalListing.objects.filter(
            provider=cart_item.product.default_source,
            product=cart_item.product,
            variant=cart_item.variant,
        ).first()
        if not listing:
            listing = ExternalListing.objects.filter(
                provider=cart_item.product.default_source,
                product=cart_item.product,
                variant__isnull=True,
            ).first()
        return listing.external_listing_id if listing else ''


class CheckoutSuccessView(LoginRequiredMixin, TemplateView):
    template_name = 'checkout/success.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self._get_order()
        session_id = self.request.GET.get('session_id')
        if session_id and session_id != '{CHECKOUT_SESSION_ID}':
            try:
                order = finalize_order_from_checkout_session(session_id, order_number=self.request.GET.get('order')) or order
            except stripe.error.StripeError as exc:
                messages.error(self.request, f'Unable to verify the Stripe checkout session: {exc}')
                order = self._get_order()
            except Exception:
                logger.exception(
                    'Checkout success finalization failed for order=%s session_id=%s',
                    self.request.GET.get('order'),
                    session_id,
                )
                site_name = StoreSettings.current().name
                messages.error(self.request, f'Stripe confirmed the redirect, but {site_name} could not finish local order processing yet. The webhook can still complete the order shortly.')
                order = self._get_order()
        context['order'] = order
        return context

    def _get_order(self):
        order = Order.objects.filter(number=self.request.GET.get('order')).select_related('user').first()
        if order and order.user_id and order.user_id != self.request.user.pk:
            raise PermissionDenied
        return order


class CheckoutCancelView(LoginRequiredMixin, TemplateView):
    template_name = 'checkout/cancel.html'
