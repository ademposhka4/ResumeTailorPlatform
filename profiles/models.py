"""
Profiles app models

JobSeekerProfile model for storing user preferences and location data.
"""
from django.conf import settings
from django.db import models


class JobSeekerProfile(models.Model):
    """
    Profile model for job seekers.
    
    Stores location, radius preferences, and default resume URL
    to avoid re-entering data for each session.
    """
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    location = models.CharField(max_length=255, blank=True)
    preferred_radius_km = models.IntegerField(default=25)
    default_resume_url = models.URLField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Profile for {self.user.username}"
    
    class Meta:
        verbose_name = 'Job Seeker Profile'
        verbose_name_plural = 'Job Seeker Profiles'
