from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalog.models import Product, ProductVariant

from .models import Cart, CartItem


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
    return render(request, 'cart/detail.html', {'cart': cart})


@require_POST
def add_to_cart(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    variant_id = request.POST.get('variant_id')
    quantity = max(int(request.POST.get('quantity', 1)), 1)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product, is_active=True) if variant_id else product.primary_variant
    cart = get_or_create_cart(request)
    item, created = CartItem.objects.get_or_create(cart=cart, variant=variant, defaults={'product': product, 'quantity': quantity})
    if not created:
        item.quantity += quantity
        item.save(update_fields=['quantity', 'updated_at'])
    messages.success(request, f'{product.name} added to your cart.')
    return redirect('cart:detail')


@require_POST
def update_cart_item(request, pk):
    cart = get_or_create_cart(request)
    item = get_object_or_404(CartItem, pk=pk, cart=cart)
    quantity = max(int(request.POST.get('quantity', 1)), 0)
    if quantity == 0:
        item.delete()
        messages.info(request, 'Item removed from your cart.')
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
