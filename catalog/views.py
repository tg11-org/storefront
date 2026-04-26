from typing import cast
from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.http import HttpResponseBadRequest, JsonResponse
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.text import Truncator
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from .models import Product, StorePage, StoreSettings


def _site_url() -> str:
    return getattr(settings, 'SITE_URL', 'https://shop.tg11.org').rstrip('/')


def _store_settings() -> StoreSettings:
    return StoreSettings.current()


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
        store = _store_settings()
        context['featured_products'] = Product.objects.filter(is_active=True, is_featured=True).prefetch_related('images')[:6]
        context['latest_products'] = Product.objects.filter(is_active=True).prefetch_related('images')[:8]
        context['meta_title'] = store.name
        context['meta_description'] = store.tagline
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
        store = _store_settings()
        context['meta_title'] = f'Products | {store.name}'
        context['meta_description'] = f'Browse products available now at {store.name}.'
        context['meta_url'] = self.request.build_absolute_uri()
        context['meta_type'] = 'website'
        context['twitter_card'] = 'summary'
        return context


class StorePageListView(ListView):
    model = StorePage
    template_name = 'catalog/page_list.html'

    def get_queryset(self):
        return StorePage.objects.filter(is_published=True).prefetch_related('products')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        store = _store_settings()
        context['meta_title'] = f'Pages | {store.name}'
        context['meta_description'] = f'Browse curated pages and collections from {store.name}.'
        context['meta_url'] = self.request.build_absolute_uri()
        context['meta_type'] = 'website'
        context['twitter_card'] = 'summary'
        return context


class ProductDetailView(DetailView):
    model = Product
    slug_field = 'slug'
    template_name = 'catalog/product_detail.html'

    def get_queryset(self):
        return Product.objects.filter(is_active=True).prefetch_related('variants', 'images', 'videos')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = cast(Product, self.get_object())
        store = _store_settings()

        raw_description = product.short_description or strip_tags(product.description)
        description = Truncator(raw_description).chars(180)

        image_obj = getattr(product, 'images').first()
        image_url = _absolute_uri(self.request, image_obj.image.url if image_obj else '')
        product_url = self.request.build_absolute_uri(product.get_absolute_url())

        context['meta_title'] = f'{product.name} | {store.name}'
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
        page = cast(StorePage, self.get_object())
        store = _store_settings()

        description_source = page.summary or strip_tags(page.body)
        description = Truncator(description_source).chars(180)

        # Prefer the page hero image; otherwise reuse first linked product image.
        if page.hero_image:
            image_url = _absolute_uri(self.request, page.hero_image.url)
        else:
            first_product = page.products.filter(is_active=True).prefetch_related('images').first()
            image_obj = getattr(first_product, 'images').first() if first_product else None
            image_url = _absolute_uri(self.request, image_obj.image.url if image_obj else '')

        context['meta_title'] = f'{page.title} | {store.name}'
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

        image_obj = getattr(product, 'images').first()
        thumbnail_url = _absolute_uri(request, image_obj.image.url if image_obj else '')
        product_url = request.build_absolute_uri(product.get_absolute_url())
        description = Truncator(product.short_description or strip_tags(product.description)).chars(180)

        store = _store_settings()
        payload = {
            'version': '1.0',
            'type': 'rich',
            'provider_name': store.name,
            'provider_url': _site_url(),
            'title': product.name,
            'author_name': store.name,
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
