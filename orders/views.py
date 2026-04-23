from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView

from .models import Order


class OrderListView(LoginRequiredMixin, ListView):
    model = Order
    template_name = 'orders/order_list.html'

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items')


class OrderDetailView(LoginRequiredMixin, DetailView):
    model = Order
    slug_field = 'number'
    slug_url_kwarg = 'number'
    template_name = 'orders/order_detail.html'

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items')
