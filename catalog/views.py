from django.views.generic import DetailView, ListView, TemplateView

from .models import Product


class HomeView(TemplateView):
    template_name = 'catalog/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['featured_products'] = Product.objects.filter(is_active=True, is_featured=True)[:6]
        context['latest_products'] = Product.objects.filter(is_active=True)[:8]
        return context


class ProductListView(ListView):
    model = Product
    template_name = 'catalog/product_list.html'
    paginate_by = 12

    def get_queryset(self):
        return Product.objects.filter(is_active=True).prefetch_related('variants', 'images')


class ProductDetailView(DetailView):
    model = Product
    slug_field = 'slug'
    template_name = 'catalog/product_detail.html'

    def get_queryset(self):
        return Product.objects.filter(is_active=True).prefetch_related('variants', 'images')
