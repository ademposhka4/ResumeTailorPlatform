from django.contrib import admin
from .models import JobSeekerProfile


@admin.register(JobSeekerProfile)
class JobSeekerProfileAdmin(admin.ModelAdmin):
    """Admin interface for JobSeekerProfile."""
    
    list_display = ['user', 'location', 'preferred_radius_km', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['user__username', 'user__email', 'location']
    readonly_fields = ['created_at', 'updated_at']
