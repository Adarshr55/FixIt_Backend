from django.contrib import admin
from .models import ServiceCategory, ProviderService, ProviderAvailability

@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'group', 'is_active', 'is_featured', 'display_order', 'created_at')
    list_filter = ('group', 'is_active', 'is_featured')
    search_fields = ('name', 'description', 'short_description')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('display_order', 'name')
    list_editable = ('is_active', 'is_featured', 'display_order')

@admin.register(ProviderService)
class ProviderServiceAdmin(admin.ModelAdmin):
    list_display = ('provider', 'category', 'verification_status', 'base_charge', 'hourly_rate', 'is_active')
    list_filter = ('verification_status', 'is_active', 'category')
    search_fields = ('provider__full_name', 'provider__user__email', 'category__name')
    list_editable = ('verification_status', 'is_active')

@admin.register(ProviderAvailability)
class ProviderAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('provider', 'day', 'start_time', 'end_time', 'is_active', 'emergency_available')
    list_filter = ('day', 'is_active', 'emergency_available')
    search_fields = ('provider__full_name', 'provider__user__email')

