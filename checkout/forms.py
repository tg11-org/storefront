from django import forms

from accounts.models import Address


class CheckoutForm(forms.Form):
    email = forms.EmailField(required=False)
    shipping_address = forms.ModelChoiceField(queryset=Address.objects.none(), required=False, empty_label='Use a new shipping address')
    full_name = forms.CharField(max_length=255, required=False)
    company_name = forms.CharField(max_length=255, required=False)
    line1 = forms.CharField(max_length=255, required=False)
    line2 = forms.CharField(max_length=255, required=False)
    city = forms.CharField(max_length=120, required=False)
    state = forms.CharField(max_length=120, required=False)
    postal_code = forms.CharField(max_length=32, required=False)
    country = forms.CharField(max_length=2, initial='US', required=False)
    phone_number = forms.CharField(max_length=32, required=False)
    save_address = forms.BooleanField(required=False, initial=True)
    same_as_shipping = forms.BooleanField(required=False, initial=True)
    billing_address = forms.ModelChoiceField(queryset=Address.objects.none(), required=False, empty_label='Use shipping address')
    billing_full_name = forms.CharField(max_length=255, required=False)
    billing_line1 = forms.CharField(max_length=255, required=False)
    billing_line2 = forms.CharField(max_length=255, required=False)
    billing_city = forms.CharField(max_length=120, required=False)
    billing_state = forms.CharField(max_length=120, required=False)
    billing_postal_code = forms.CharField(max_length=32, required=False)
    billing_country = forms.CharField(max_length=2, initial='US', required=False)
    coupon_code = forms.CharField(max_length=48, required=False)
    shipping_rate_rule = forms.CharField(max_length=255, required=False)
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}), required=False)

    def __init__(self, user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        address_qs = user.addresses.all() if getattr(user, 'is_authenticated', False) else Address.objects.none()
        self.fields['shipping_address'].queryset = address_qs
        self.fields['billing_address'].queryset = address_qs
        if not getattr(user, 'is_authenticated', False):
            self.fields['email'].required = True

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('shipping_address'):
            for field_name in ['full_name', 'line1', 'city', 'postal_code', 'country']:
                if not cleaned.get(field_name):
                    self.add_error(field_name, 'This field is required for a new shipping address.')
        if not cleaned.get('same_as_shipping') and not cleaned.get('billing_address'):
            for field_name in ['billing_full_name', 'billing_line1', 'billing_city', 'billing_postal_code', 'billing_country']:
                if not cleaned.get(field_name):
                    self.add_error(field_name, 'This field is required for billing.')
        return cleaned
