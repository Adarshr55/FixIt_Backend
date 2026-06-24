from django.contrib import admin
from .models import PromoBanner, CMSSection, HowItWorksStep

@admin.register(PromoBanner)
class PromoBannerAdmin(admin.ModelAdmin):
    list_display = ('title', 'coupon_code', 'discount_percent', 'discount_amount', 'is_active', 'start_date', 'end_date', 'display_order')
    list_filter = ('is_active', 'start_date', 'end_date')
    search_fields = ('title', 'coupon_code', 'subtitle')
    list_editable = ('is_active', 'display_order')
    ordering = ('display_order', '-created_at')

@admin.register(CMSSection)
class CMSSectionAdmin(admin.ModelAdmin):
    list_display = ('section_key', 'title', 'is_active', 'updated_at')
    list_filter = ('is_active', 'section_key')
    search_fields = ('section_key', 'title', 'subtitle', 'body')
    list_editable = ('is_active',)

@admin.register(HowItWorksStep)
class HowItWorksStepAdmin(admin.ModelAdmin):
    list_display = ('step_number', 'title', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('title', 'description')
    ordering = ('step_number',)

