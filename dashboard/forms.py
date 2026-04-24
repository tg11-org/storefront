from __future__ import annotations

import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from catalog.models import Product, ProductVariant, StorePage
from connectors.models import ChannelAccount, ExternalListing


class ProductCreateForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            'name',
            'slug',
            'short_description',
            'description',
            'product_type',
            'default_source',
            'allow_custom_requests',
            'custom_request_label',
            'custom_request_help_text',
            'is_active',
            'is_featured',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'custom_request_help_text': forms.TextInput(attrs={'placeholder': 'Example: color palette, size notes, gift message'}),
        }

    def clean_slug(self):
        slug = self.cleaned_data.get('slug') or slugify(self.cleaned_data.get('name', ''))
        if Product.objects.filter(slug=slug).exists():
            raise ValidationError('A product with this slug already exists.')
        return slug


class DefaultVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ('title', 'sku', 'price', 'compare_at_price', 'stock_quantity', 'is_active')


class StorePageCreateForm(forms.ModelForm):
    class Meta:
        model = StorePage
        fields = ('title', 'slug', 'summary', 'body', 'products', 'is_published', 'sort_order')
        widgets = {
            'body': forms.Textarea(attrs={'rows': 7}),
            'products': forms.SelectMultiple(attrs={'size': 8}),
        }

    def clean_slug(self):
        slug = self.cleaned_data.get('slug') or slugify(self.cleaned_data.get('title', ''))
        if StorePage.objects.filter(slug=slug).exists():
            raise ValidationError('A page with this slug already exists.')
        return slug


class ChannelAccountCreateForm(forms.ModelForm):
    config_text = forms.CharField(
        label='Config JSON',
        required=False,
        widget=forms.Textarea(attrs={'rows': 7, 'placeholder': '{"api_key": "...", "shop_id": "..."}'}),
        help_text='Optional provider settings as JSON. Store sensitive long-lived credentials in env vars where possible.',
    )

    class Meta:
        model = ChannelAccount
        fields = ('provider', 'name', 'account_identifier', 'access_token', 'refresh_token', 'is_active', 'sync_enabled')
        widgets = {
            'access_token': forms.PasswordInput(render_value=True),
            'refresh_token': forms.PasswordInput(render_value=True),
        }

    def clean_config_text(self):
        value = self.cleaned_data.get('config_text', '').strip()
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError(f'Config JSON is invalid: {exc.msg}') from exc
        if not isinstance(parsed, dict):
            raise ValidationError('Config JSON must be an object.')
        return parsed

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.config = self.cleaned_data['config_text']
        if commit:
            instance.save()
        return instance


class ExternalListingCreateForm(forms.ModelForm):
    class Meta:
        model = ExternalListing
        fields = ('channel_account', 'product', 'variant', 'external_listing_id', 'external_product_id', 'external_variant_id', 'listing_url')

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get('product')
        variant = cleaned.get('variant')
        if variant and product and variant.product_id != product.pk:
            raise ValidationError('The selected variant must belong to the selected product.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.provider = instance.channel_account.provider
        if commit:
            instance.save()
        return instance
