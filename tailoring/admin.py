from django.contrib import admin
from .models import TailoringSession


@admin.register(TailoringSession)
class TailoringSessionAdmin(admin.ModelAdmin):
    """Admin interface for TailoringSession."""
    
    list_display = [
        'id',
        'user',
        'job',
        'generated_title',
        'status',
        'created_at',
        'updated_at'
    ]
    list_filter = ['status', 'created_at', 'updated_at']
    search_fields = [
        'user__username',
        'job__title',
        'job__company',
        'generated_title'
    ]
    readonly_fields = [
        'created_at',
        'updated_at',
        'completed_at',
        'token_usage',
        'openai_run_id',
        'output_metadata',
    ]
    
    fieldsets = (
        ('Session Info', {
            'fields': ('user', 'job', 'status', 'openai_run_id', 'completed_at')
        }),
        ('Input Data', {
            'fields': ('job_snapshot', 'input_experience_snapshot', 'parameters'),
            'classes': ('collapse',)
        }),
        ('Generated Output', {
            'fields': (
                'generated_title',
                'generated_bullets',
                'generated_sections',
                'tailored_resume',
                'cover_letter',
                'ai_suggestions',
                'token_usage',
                'output_metadata',
                'debug_log',
                'error_message',
            )
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at')
        }),
    )
