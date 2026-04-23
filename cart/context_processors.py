from .views import get_or_create_cart


def cart_summary(request):
    cart = get_or_create_cart(request, create=False)
    return {'site_cart': cart}
