from __future__ import annotations

import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from catalog.models import Product, ProductVariant, StorePage, ProductImage, ProductVideo
from connectors.models import ChannelAccount, ExternalListing
from orders.models import FulfillmentUpdate, Order


class ProductCreateForm(forms.ModelForm):
    image_1 = forms.ImageField(required=False, label='Image 1')
    image_2 = forms.ImageField(required=False, label='Image 2')
    image_3 = forms.ImageField(required=False, label='Image 3')
    image_4 = forms.ImageField(required=False, label='Image 4')
    image_5 = forms.ImageField(required=False, label='Image 5')
    video_file = forms.FileField(required=False, label='Product video')
    video_thumbnail = forms.ImageField(required=False, label='Video thumbnail')
    video_title = forms.CharField(required=False, label='Video title', max_length=255)

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ['image_1', 'image_2', 'image_3', 'image_4', 'image_5']:
            self.fields[field_name].widget = forms.FileInput(attrs={'class': 'form-input', 'accept': 'image/*'})
        self.fields['video_file'].widget = forms.FileInput(attrs={'class': 'form-input', 'accept': 'video/mp4,video/webm,video/ogg'})
        self.fields['video_thumbnail'].widget = forms.FileInput(attrs={'class': 'form-input', 'accept': 'image/*'})
        self.fields['video_title'].widget = forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Optional video title'})
        self.fields['video_file'].help_text = 'Optional: upload one MP4, WebM, or Ogg product video.'

    def clean_slug(self):
        slug = self.cleaned_data.get('slug') or slugify(self.cleaned_data.get('name', ''))
        if Product.objects.filter(slug=slug).exists():
            raise ValidationError('A product with this slug already exists.')
        return slug

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('video_thumbnail') and not cleaned.get('video_file'):
            self.add_error('video_thumbnail', 'Upload a video before adding a thumbnail.')
        if cleaned.get('video_title') and not cleaned.get('video_file'):
            self.add_error('video_title', 'Upload a video before adding a title.')
        return cleaned


class DefaultVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ('title', 'sku', 'price', 'compare_at_price', 'stock_quantity', 'max_order_quantity', 'is_active')


class StorePageCreateForm(forms.ModelForm):
    class Meta:
        model = StorePage
        fields = ('title', 'slug', 'summary', 'hero_image', 'body', 'products', 'is_published', 'sort_order')
        widgets = {
            'body': forms.Textarea(attrs={'rows': 7}),
            'products': forms.SelectMultiple(attrs={'size': 8}),
            'hero_image': forms.FileInput(attrs={'class': 'form-input', 'accept': 'image/*'}),
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


class FulfillmentUpdateForm(forms.ModelForm):
    """Form for creating fulfillment status updates."""
    
    class Meta:
        model = FulfillmentUpdate
        fields = ['status', 'tracking_number', 'carrier', 'tracking_url', 'estimated_delivery', 'notes']
        widgets = {
            'status': forms.Select(attrs={
                'class': 'form-select',
            }),
            'tracking_number': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., 1Z999AA10123456784',
            }),
            'carrier': forms.Select(attrs={
                'class': 'form-select',
            }),
            'tracking_url': forms.URLInput(attrs={
                'class': 'form-input',
                'placeholder': 'https://...',
            }),
            'estimated_delivery': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-input',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Additional details for the customer (e.g., "Package arriving Tuesday between 9am-5pm")',
            }),
        }


class OrderFilterForm(forms.Form):
    """Form for filtering orders on the management page."""
    
    STATUS_CHOICES = [('', 'All statuses')] + list(Order.Status.choices)
    FULFILLMENT_STATUS_CHOICES = [('', 'All fulfillment statuses')] + list(Order.FulfillmentStatus.choices)
    SOURCE_CHOICES = [('', 'All sources')] + list(Order.Source.choices)
    
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False, widget=forms.Select(attrs={
        'class': 'form-select',
    }))
    fulfillment_status = forms.ChoiceField(choices=FULFILLMENT_STATUS_CHOICES, required=False, widget=forms.Select(attrs={
        'class': 'form-select',
    }))
    source = forms.ChoiceField(choices=SOURCE_CHOICES, required=False, widget=forms.Select(attrs={
        'class': 'form-select',
    }))
    search = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'form-input',
        'placeholder': 'Search by order number or email...',
    }))


class BulkOrderActionForm(forms.Form):
    """Form for bulk actions on multiple orders."""
    
    ACTION_CHOICES = [
        ('', 'Select action'),
        ('mark_queued', 'Mark as Queued'),
        ('mark_in_progress', 'Mark as In Progress'),
        ('mark_shipped', 'Mark as Shipped'),
        ('mark_delivered', 'Mark as Delivered'),
    ]
    
    action = forms.ChoiceField(choices=ACTION_CHOICES, widget=forms.Select(attrs={
        'class': 'form-select',
    }))
    order_ids = forms.CharField(widget=forms.HiddenInput())
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={
        'class': 'form-textarea',
        'rows': 2,
        'placeholder': 'Optional notes for affected customers',
    }))


class OrderRefundForm(forms.Form):
    """Form for issuing refunds."""
    
    reason = forms.CharField(
        label='Refund reason',
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 3,
            'placeholder': 'Explain why this order is being refunded',
        })
    )
    confirm = forms.BooleanField(
        label='I confirm this refund should be processed',
        widget=forms.CheckboxInput(attrs={
            'class': 'form-checkbox',
        })
    )


class ProductImageForm(forms.ModelForm):
    """Form for uploading product images (max 5 per product)."""
    
    class Meta:
        model = ProductImage
        fields = ('image', 'alt_text', 'sort_order')
        widgets = {
            'image': forms.FileInput(attrs={
                'class': 'form-input',
                'accept': 'image/*',
            }),
            'alt_text': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Descriptive text for accessibility',
            }),
            'sort_order': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 0,
            }),
        }


class ProductVideoForm(forms.ModelForm):
    """Form for uploading a single product video."""
    
    class Meta:
        model = ProductVideo
        fields = ('video', 'thumbnail', 'title')
        widgets = {
            'video': forms.FileInput(attrs={
                'class': 'form-input',
                'accept': 'video/mp4,video/webm,video/ogg',
                'help_text': 'Supported: MP4, WebM, Ogg (max 100MB)',
            }),
            'thumbnail': forms.FileInput(attrs={
                'class': 'form-input',
                'accept': 'image/*',
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., "Product demo" or "How to use"',
            }),
        }


class ProductImageFormSet(forms.BaseInlineFormSet):
    """Validate max 5 images per product."""
    
    def clean(self):
        super().clean()
        if self.form_errors:
            return
        
        image_count = 0
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                image_count += 1
        
        if image_count > 5:
            raise ValidationError('Maximum 5 images per product.')
