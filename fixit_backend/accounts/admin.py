from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation    import gettext_lazy as _
from .models import User

# Register your models here.
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display=[
        'email',
        'role',
        'is_active',
        'is_staff',
        'is_profile_complete',
        # 'is_phone_verified',
        # 'is_google_auth',
        'date_joined',
    ]
    
    list_filter=[
        'role',
        'is_active',
        'is_staff',
        'is_profile_complete',
        # 'is_phone_verified',
        # 'is_google_auth',
    ]

    search_fields  = ['email', 'phone']
    ordering       = ['-date_joined']
    list_per_page  = 25

    fieldsets = (
        (_('Login Info'), {
            'fields': ('email', 'password')
        }),
        (_('Personal Info'), {
            'fields': ('phone', 'role')
        }),
        (_('Status Flags'), {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                # 'is_phone_verified',
                'is_profile_complete',
                # 'is_google_auth',
                # 'is_email_verified',
            )
        }),
         (_('Permissions'), {
            'fields': ('groups', 'user_permissions'),
            'classes': ('collapse',),
            # collapse hides this section by default
            # cleaner admin view
        }),
        (_('Timestamps'), {
            'fields': ('date_joined', 'last_login', 'updated_at'),
        }),
    )


    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "phone", "role", "password1", "password2", "is_active", "is_staff"),
        }),
    )

    readonly_fields = ('date_joined', 'last_login', 'updated_at')
    filter_horizontal = ("groups", "user_permissions")
