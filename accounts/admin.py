from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import AddressForm
from .models import Address, CustomUser, CustomerProfile


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    ordering = ('email',)
    list_display = ('email', 'first_name', 'last_name', 'is_staff', 'is_active')
    search_fields = ('email', 'first_name', 'last_name')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_staff', 'is_active'),
        }),
    )


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'stripe_customer_id', 'marketing_opt_in', 'updated_at')
    search_fields = ('user__email', 'stripe_customer_id')


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    form = AddressForm
    list_display = ('full_name', 'user', 'address_type', 'city', 'state', 'country', 'is_default')
    list_filter = ('address_type', 'country', 'is_default')
    search_fields = ('full_name', 'user__email', 'line1', 'city', 'postal_code')
