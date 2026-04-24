from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import FormView, TemplateView

from accounts.models import Address
from cart.views import get_or_create_cart
from connectors.models import ExternalListing
from orders.models import Order, OrderItem
from payments.services import StripeConfigurationError, create_checkout_session, finalize_order_from_checkout_session

from .forms import CheckoutForm


class CheckoutView(LoginRequiredMixin, FormView):
    template_name = 'checkout/checkout.html'
    form_class = CheckoutForm

    def dispatch(self, request, *args, **kwargs):
        self.cart = get_or_create_cart(request)
        if not self.cart or not self.cart.items.exists():
            messages.info(request, 'Your cart is empty.')
            return redirect('cart:detail')
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cart'] = self.cart
        return context

    def form_valid(self, form):
        shipping_address = self._resolve_shipping_address(form)
        billing_address = self._resolve_billing_address(form, shipping_address)
        order = self._build_order(form, shipping_address, billing_address)
        try:
            session = create_checkout_session(
                order,
                self.request.build_absolute_uri(reverse('checkout:success')) + f'?order={order.number}&session_id={{CHECKOUT_SESSION_ID}}',
                self.request.build_absolute_uri(reverse('checkout:cancel')) + f'?order={order.number}',
            )
        except StripeConfigurationError as exc:
            order.status = Order.Status.FAILED
            order.save(update_fields=['status', 'updated_at'])
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        return redirect(session.url, permanent=False)

    def _resolve_shipping_address(self, form):
        address = form.cleaned_data['shipping_address']
        if address:
            return address
        address = Address.objects.create(
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
        if address.is_default:
            self.request.user.addresses.filter(address_type=Address.AddressType.SHIPPING).exclude(pk=address.pk).update(is_default=False)
        return address

    def _resolve_billing_address(self, form, shipping_address):
        if form.cleaned_data['same_as_shipping']:
            return shipping_address
        address = form.cleaned_data['billing_address']
        if address:
            return address
        return Address.objects.create(
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

    def _build_order(self, form, shipping_address, billing_address):
        source = Order.Source.INTERNAL
        cart_items = self.cart.items.select_related('product', 'variant')
        if any(item.product.default_source == 'etsy' for item in cart_items):
            source = Order.Source.ETSY
        elif any(item.product.default_source == 'popcustoms' for item in cart_items):
            source = Order.Source.POPCUSTOMS

        subtotal = self.cart.subtotal
        order = Order.objects.create(
            user=self.request.user,
            cart=self.cart,
            email=self.request.user.email,
            status=Order.Status.PENDING_PAYMENT,
            source=source,
            sync_state=Order.SyncState.PENDING if source != Order.Source.INTERNAL else Order.SyncState.NOT_APPLICABLE,
            shipping_address=shipping_address.as_dict(),
            billing_address=billing_address.as_dict(),
            subtotal=subtotal,
            grand_total=subtotal,
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
            )
            for cart_item in cart_items
        ])
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
        order = Order.objects.filter(number=self.request.GET.get('order'), user=self.request.user).first()
        session_id = self.request.GET.get('session_id')
        if session_id and session_id != '{CHECKOUT_SESSION_ID}':
            order = finalize_order_from_checkout_session(session_id) or order
        context['order'] = order
        return context


class CheckoutCancelView(LoginRequiredMixin, TemplateView):
    template_name = 'checkout/cancel.html'
