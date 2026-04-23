from django import forms

from .models import Address


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = [
            'label',
            'address_type',
            'full_name',
            'company_name',
            'line1',
            'line2',
            'city',
            'state',
            'postal_code',
            'country',
            'phone_number',
            'is_default',
        ]
