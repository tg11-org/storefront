from django.contrib import admin

from .models import Product, ProductImage, ProductVariant, StorePage, ProductVideo, StoreSettings


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ('sort_order', 'title', 'size_label', 'sku', 'price', 'compare_at_price', 'stock_quantity', 'max_order_quantity', 'weight_oz', 'is_default', 'is_active')
    ordering = ('sort_order', 'id')


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    max_num = 10
    ordering = ('sort_order',)
    fields = ('image', 'alt_text', 'sort_order')


class ProductVideoInline(admin.StackedInline):
    model = ProductVideo
    extra = 0
    max_num = 2
    ordering = ('sort_order',)
    fields = ('video', 'thumbnail', 'title', 'sort_order')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'product_type', 'default_source', 'allow_custom_requests', 'is_active', 'is_featured')
    list_filter = ('product_type', 'default_source', 'allow_custom_requests', 'is_active', 'is_featured')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'slug', 'short_description')
    inlines = [ProductVariantInline, ProductImageInline, ProductVideoInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('sku', 'product', 'sort_order', 'title', 'size_label', 'price', 'stock_quantity', 'max_order_quantity', 'weight_oz', 'is_active')
    list_filter = ('is_active', 'is_default')
    search_fields = ('sku', 'product__name', 'title')
    fieldsets = (
        (None, {'fields': ('product', 'sort_order', 'title', 'size_label', 'sku', 'price', 'compare_at_price', 'stock_quantity', 'max_order_quantity', 'is_default', 'is_active')}),
        ('Shipping', {'fields': ('weight_oz', 'length_in', 'width_in', 'height_in', 'origin_country', 'hs_code')}),
        ('Apparel sizing', {'fields': ('chest_width_in', 'body_length_in', 'sleeve_length_in')}),
        ('Supplier pricing', {'fields': ('supplier_price', 'supplier_compare_at', 'supplier_sale_price', 'supplier_sale_start', 'supplier_sale_end', 'last_sync_at')}),
    )


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'variant', 'sort_order')
    list_filter = ('product',)


@admin.register(ProductVideo)
class ProductVideoAdmin(admin.ModelAdmin):
    list_display = ('product', 'title', 'sort_order', 'uploaded_at')
    search_fields = ('product__name', 'title')


@admin.register(StorePage)
class StorePageAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'is_published', 'sort_order', 'updated_at')
    list_filter = ('is_published',)
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ('title', 'slug', 'summary', 'body')
    filter_horizontal = ('products',)


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    list_display = ('name', 'support_email', 'currency', 'free_shipping_threshold', 'order_prefix', 'updated_at')

    def has_add_permission(self, request):
        return not StoreSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
