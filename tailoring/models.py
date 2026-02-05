"""
Tailoring app models

TailoringSession model for storing AI-generated resume tailoring history.
"""
from django.conf import settings
from django.db import models


class TailoringSession(models.Model):
    """
    Store history of AI tailoring sessions.
    
    Each session represents one attempt to tailor a user's experience
    to a specific job posting using AI.
    """
    
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSING = 'PROCESSING', 'Processing'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tailoring_sessions',
    )
    job = models.ForeignKey(
        'jobs.JobPosting',
        on_delete=models.CASCADE,
        related_name='tailoring_sessions',
    )

    # Snapshot of job data at time of tailoring
    job_snapshot = models.JSONField(default=dict, blank=True)
    
    # Snapshot of experience at time of tailoring
    input_experience_snapshot = models.JSONField(default=dict, blank=True)

    # Tailoring parameters selected by the user
    parameters = models.JSONField(default=dict, blank=True)
    
    # AI-generated outputs
    generated_title = models.CharField(max_length=255, blank=True)
    generated_bullets = models.JSONField(default=list, blank=True)  # List of bullet strings
    generated_sections = models.JSONField(default=list, blank=True)
    tailored_resume = models.TextField(blank=True)
    cover_letter = models.TextField(blank=True)
    ai_suggestions = models.TextField(blank=True)

    # AI runtime metadata
    openai_run_id = models.CharField(max_length=255, blank=True)
    token_usage = models.JSONField(default=dict, blank=True)
    output_metadata = models.JSONField(default=dict, blank=True)
    debug_log = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Tailoring session for {self.user.username} - {self.job.title}"
    
    class Meta:
        verbose_name = 'Tailoring Session'
        verbose_name_plural = 'Tailoring Sessions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
        ]
