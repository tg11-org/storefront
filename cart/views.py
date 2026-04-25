from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalog.models import Product, ProductVariant
from pricing.services import calculate_cart_totals

from .models import Cart, CartItem


def _posted_quantity(request, default: int, minimum: int) -> int:
    try:
        quantity = int(request.POST.get('quantity', default))
    except (TypeError, ValueError):
        return default
    return max(quantity, minimum)


def _requested_quantity(cart: Cart, variant: ProductVariant, quantity: int, exclude_item: CartItem | None = None) -> int:
    existing_items = cart.items.filter(variant=variant)
    if exclude_item:
        existing_items = existing_items.exclude(pk=exclude_item.pk)
    existing_quantity = sum(item.quantity for item in existing_items)
    return existing_quantity + quantity


def _has_stock(variant: ProductVariant, quantity: int) -> bool:
    return quantity <= variant.stock_quantity


def _within_order_limit(variant: ProductVariant, quantity: int) -> bool:
    return quantity <= variant.effective_max_order_quantity


def _quantity_error_message(variant: ProductVariant, product: Product) -> str:
    if variant.max_order_quantity is not None and variant.max_order_quantity < variant.stock_quantity:
        return (
            f'Maximum {variant.max_order_quantity} per order for {product.name}. '
            f'{variant.stock_quantity} currently in stock.'
        )
    return f'Only {variant.stock_quantity} available for {product.name}.'


def get_or_create_cart(request, create: bool = True) -> Cart | None:
    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user, checked_out_at__isnull=True).first()
        if cart or not create:
            return cart
        return Cart.objects.create(user=request.user)

    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key
    cart = Cart.objects.filter(session_key=session_key, checked_out_at__isnull=True).first()
    if cart or not create:
        return cart
    return Cart.objects.create(session_key=session_key)


def cart_detail(request):
    cart = get_or_create_cart(request)
    totals = calculate_cart_totals(cart, request.user if request.user.is_authenticated else None, coupon_code=cart.applied_coupon_code) if cart else None
    return render(request, 'cart/detail.html', {'cart': cart, 'totals': totals})


@require_POST
def apply_coupon(request):
    cart = get_or_create_cart(request)
    code = request.POST.get('coupon_code', '').strip().upper()
    totals = calculate_cart_totals(cart, request.user if request.user.is_authenticated else None, coupon_code=code)
    rejected = next((rule for rule in totals.applied_rules if rule.kind == 'coupon_rejected'), None)
    if rejected:
        messages.error(request, rejected.label)
    elif totals.coupon:
        cart.applied_coupon_code = totals.coupon.code
        cart.save(update_fields=['applied_coupon_code', 'updated_at'])
        messages.success(request, f'Coupon {totals.coupon.code} applied.')
    else:
        messages.error(request, 'Enter a valid coupon code.')
    return redirect('cart:detail')


@require_POST
def remove_coupon(request):
    cart = get_or_create_cart(request)
    cart.applied_coupon_code = ''
    cart.save(update_fields=['applied_coupon_code', 'updated_at'])
    messages.info(request, 'Coupon removed.')
    return redirect('cart:detail')


@require_POST
def add_to_cart(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    variant_id = request.POST.get('variant_id')
    quantity = _posted_quantity(request, 1, 1)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product, is_active=True) if variant_id else product.primary_variant
    custom_request = request.POST.get('custom_request', '').strip() if product.allow_custom_requests else ''
    cart = get_or_create_cart(request)
    requested_total = _requested_quantity(cart, variant, quantity) if variant else 0
    if not variant or not _has_stock(variant, requested_total) or not _within_order_limit(variant, requested_total):
        messages.error(request, _quantity_error_message(variant, product) if variant else f'Only 0 available for {product.name}.')
        return redirect(product.get_absolute_url())
    item, created = CartItem.objects.get_or_create(cart=cart, variant=variant, custom_request=custom_request, defaults={'product': product, 'quantity': quantity})
    if not created:
        item.quantity += quantity
        item.save(update_fields=['quantity', 'updated_at'])
    messages.success(request, f'{product.name} added to your cart.')
    return redirect('cart:detail')


@require_POST
def update_cart_item(request, pk):
    cart = get_or_create_cart(request)
    item = get_object_or_404(CartItem, pk=pk, cart=cart)
    quantity = _posted_quantity(request, 1, 0)
    if quantity == 0:
        item.delete()
        messages.info(request, 'Item removed from your cart.')
    elif (
        not _has_stock(item.variant, _requested_quantity(cart, item.variant, quantity, exclude_item=item))
        or not _within_order_limit(item.variant, _requested_quantity(cart, item.variant, quantity, exclude_item=item))
    ):
        messages.error(request, _quantity_error_message(item.variant, item.product))
    else:
        item.quantity = quantity
        item.save(update_fields=['quantity', 'updated_at'])
        messages.success(request, 'Cart updated.')
    return redirect('cart:detail')


@require_POST
def remove_cart_item(request, pk):
    cart = get_or_create_cart(request)
    item = get_object_or_404(CartItem, pk=pk, cart=cart)
    item.delete()
    messages.info(request, 'Item removed from your cart.')
    return redirect('cart:detail')
