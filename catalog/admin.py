from django.contrib import admin

from .models import Product, ProductImage, ProductVariant, StorePage, ProductVideo


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ('title', 'sku', 'price', 'compare_at_price', 'stock_quantity', 'max_order_quantity', 'is_default', 'is_active')


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    max_num = 5
    ordering = ('sort_order',)
    fields = ('image', 'alt_text', 'sort_order')


class ProductVideoInline(admin.StackedInline):
    model = ProductVideo
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'product_type', 'default_source', 'allow_custom_requests', 'is_active', 'is_featured')
    list_filter = ('product_type', 'default_source', 'allow_custom_requests', 'is_active', 'is_featured')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'slug', 'short_description')
    inlines = [ProductVariantInline, ProductImageInline, ProductVideoInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('sku', 'product', 'title', 'price', 'stock_quantity', 'max_order_quantity', 'is_active')
    list_filter = ('is_active', 'is_default')
    search_fields = ('sku', 'product__name', 'title')


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'variant', 'sort_order')
    list_filter = ('product',)


@admin.register(ProductVideo)
class ProductVideoAdmin(admin.ModelAdmin):
    list_display = ('product', 'title', 'uploaded_at')
    search_fields = ('product__name', 'title')


@admin.register(StorePage)
class StorePageAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'is_published', 'sort_order', 'updated_at')
    list_filter = ('is_published',)
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ('title', 'slug', 'summary', 'body')
    filter_horizontal = ('products',)
