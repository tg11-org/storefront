from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.http import HttpResponseBadRequest, JsonResponse
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.text import Truncator
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from .models import Product, StorePage


def _site_url() -> str:
    return getattr(settings, 'SITE_URL', 'https://shop.tg11.org').rstrip('/')


def _absolute_uri(request, value: str | None) -> str:
    if not value:
        return ''
    if value.startswith('http://') or value.startswith('https://'):
        return value
    return request.build_absolute_uri(value)


class HomeView(TemplateView):
    template_name = 'catalog/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['featured_products'] = Product.objects.filter(is_active=True, is_featured=True)[:6]
        context['latest_products'] = Product.objects.filter(is_active=True)[:8]
        context['meta_title'] = 'TG11 Shop'
        context['meta_description'] = 'Quality goods, secure checkout, and fast fulfillment from TG11 Shop.'
        context['meta_url'] = self.request.build_absolute_uri()
        context['meta_type'] = 'website'
        context['twitter_card'] = 'summary'
        return context


class ProductListView(ListView):
    model = Product
    template_name = 'catalog/product_list.html'
    paginate_by = 12

    def get_queryset(self):
        return Product.objects.filter(is_active=True).prefetch_related('variants', 'images')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['meta_title'] = 'Products | TG11 Shop'
        context['meta_description'] = 'Browse products available now at TG11 Shop.'
        context['meta_url'] = self.request.build_absolute_uri()
        context['meta_type'] = 'website'
        context['twitter_card'] = 'summary'
        return context


class ProductDetailView(DetailView):
    model = Product
    slug_field = 'slug'
    template_name = 'catalog/product_detail.html'

    def get_queryset(self):
        return Product.objects.filter(is_active=True).prefetch_related('variants', 'images')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object

        raw_description = product.short_description or strip_tags(product.description)
        description = Truncator(raw_description).chars(180)

        image_obj = product.images.first()
        image_url = _absolute_uri(self.request, image_obj.image.url if image_obj else '')
        product_url = self.request.build_absolute_uri(product.get_absolute_url())

        context['meta_title'] = f'{product.name} | TG11 Shop'
        context['meta_description'] = description
        context['meta_url'] = product_url
        context['meta_image'] = image_url
        context['meta_type'] = 'product'
        context['twitter_card'] = 'summary_large_image' if image_url else 'summary'
        context['oembed_url'] = (
            f"{self.request.build_absolute_uri(reverse('catalog:product_oembed'))}"
            f"?{urlencode({'url': product_url, 'format': 'json'})}"
        )
        return context


class StorePageDetailView(DetailView):
    model = StorePage
    slug_field = 'slug'
    template_name = 'catalog/store_page_detail.html'

    def get_queryset(self):
        return StorePage.objects.filter(is_published=True).prefetch_related('products__variants', 'products__images')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = self.object

        description_source = page.summary or strip_tags(page.body)
        description = Truncator(description_source).chars(180)

        # Reuse first linked product image as preview image when available.
        first_product = page.products.filter(is_active=True).prefetch_related('images').first()
        image_obj = first_product.images.first() if first_product else None
        image_url = _absolute_uri(self.request, image_obj.image.url if image_obj else '')

        context['meta_title'] = f'{page.title} | TG11 Shop'
        context['meta_description'] = description
        context['meta_url'] = self.request.build_absolute_uri(page.get_absolute_url())
        context['meta_image'] = image_url
        context['meta_type'] = 'article'
        context['twitter_card'] = 'summary_large_image' if image_url else 'summary'
        return context


class ProductOEmbedView(View):
    """Serve oEmbed JSON for TG11 product pages."""

    def get(self, request):
        requested_url = request.GET.get('url', '').strip()
        if not requested_url:
            return HttpResponseBadRequest('Missing url parameter.')

        parsed = urlparse(requested_url)
        path = parsed.path or ''
        prefix = reverse('catalog:product_list')
        if not path.startswith(prefix):
            return HttpResponseBadRequest('URL is not a product URL.')

        slug = path.removeprefix(prefix).strip('/').split('/')[0]
        if not slug:
            return HttpResponseBadRequest('Unable to resolve product slug from URL.')

        product = Product.objects.filter(is_active=True, slug=slug).prefetch_related('images').first()
        if not product:
            return HttpResponseBadRequest('Product not found for URL.')

        image_obj = product.images.first()
        thumbnail_url = _absolute_uri(request, image_obj.image.url if image_obj else '')
        product_url = request.build_absolute_uri(product.get_absolute_url())
        description = Truncator(product.short_description or strip_tags(product.description)).chars(180)

        payload = {
            'version': '1.0',
            'type': 'rich',
            'provider_name': 'TG11 Shop',
            'provider_url': _site_url(),
            'title': product.name,
            'author_name': 'TG11 Shop',
            'author_url': _site_url(),
            'html': f'<a href="{product_url}">{product.name}</a>',
            'width': 600,
            'height': 338,
            'url': product_url,
            'description': description,
        }
        if thumbnail_url:
            payload['thumbnail_url'] = thumbnail_url

        return JsonResponse(payload)
