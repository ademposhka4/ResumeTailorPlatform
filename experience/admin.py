from django.contrib import admin
from .models import ExperienceGraph


@admin.register(ExperienceGraph)
class ExperienceGraphAdmin(admin.ModelAdmin):
    """Admin interface for ExperienceGraph."""
    
    list_display = ['user', 'updated_at']
    list_filter = ['updated_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['updated_at']
