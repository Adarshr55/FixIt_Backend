from django.contrib import admin
from .models  import Booking, BookingStatusHistory


class BookingStatusHistoryInline(admin.TabularInline):
    model           = BookingStatusHistory
    extra           = 0
    readonly_fields = ['status', 'changed_by', 'note', 'timestamp']
    can_delete      = False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display    = ['id', 'customer', 'provider', 'category', 'status', 'booking_type', 'created_at']
    list_filter     = ['status', 'booking_type', 'category']
    search_fields   = ['customer__email', 'provider__full_name']
    readonly_fields = ['created_at', 'updated_at', 'accepted_at', 'started_at', 'completed_at']
    inlines         = [BookingStatusHistoryInline]


@admin.register(BookingStatusHistory)
class BookingStatusHistoryAdmin(admin.ModelAdmin):
    list_display    = ['booking', 'status', 'changed_by', 'timestamp']
    list_filter     = ['status']
    readonly_fields = ['booking', 'status', 'changed_by', 'note', 'timestamp']