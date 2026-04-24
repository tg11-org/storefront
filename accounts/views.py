from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from accounts.forms import AddressForm
from orders.models import Order
from payments.models import SavedPaymentMethodRef
from payments.services import sync_saved_payment_methods


class AccountDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/dashboard.html'
    success_url = reverse_lazy('accounts:dashboard')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        profile = getattr(request.user, 'profile', None)
        if profile and profile.stripe_customer_id:
            sync_saved_payment_methods(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['address_form'] = kwargs.get('address_form') or AddressForm()
        context['addresses'] = self.request.user.addresses.all()
        context['orders'] = Order.objects.filter(user=self.request.user)[:5]
        context['payment_methods'] = SavedPaymentMethodRef.objects.filter(user=self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            if address.is_default:
                request.user.addresses.filter(address_type=address.address_type).update(is_default=False)
            address.save()
            messages.success(request, 'Address saved to your account.')
            return redirect(self.success_url)
        messages.error(request, 'Please fix the address form errors and try again.')
        return self.render_to_response(self.get_context_data(address_form=form))
