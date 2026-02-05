from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin interface for custom User model."""
    
    list_display = [
        'username',
        'email',
        'role',
        'token_quota',
        'tokens_used',
        'words_used',
        'is_staff',
    ]
    list_filter = ['role', 'is_staff', 'is_superuser']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Custom Fields', {'fields': ('role', 'token_quota', 'tokens_used', 'words_used')}),
    )
    
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Custom Fields', {'fields': ('role', 'token_quota', 'tokens_used', 'words_used')}),
    )
