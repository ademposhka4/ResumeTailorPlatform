"""
Accounts app models

Custom User model extending AbstractUser with role-based access and token quota.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model with role and token quota tracking.
    
    Extends Django's AbstractUser to add:
    - role: Distinguish between admins and job seekers
    - token_quota: Maximum tokens allowed for AI operations
    - tokens_used: Track consumed tokens
    """
    
    ADMIN = 'ADMIN'
    JOB_SEEKER = 'JOB_SEEKER'
    
    ROLE_CHOICES = [
        (ADMIN, 'Admin'),
        (JOB_SEEKER, 'Job Seeker'),
    ]
    
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=JOB_SEEKER,
    )
    token_quota = models.IntegerField(default=10000)
    tokens_used = models.IntegerField(default=0)
    words_used = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.username} ({self.role})"

    @property
    def tokens_available(self) -> int:
        """
        Remaining token balance for AI operations.
        """
        return max(self.token_quota - self.tokens_used, 0)

    def record_usage(self, *, tokens: int = 0, words: int = 0) -> None:
        """
        Persist usage information after an AI request.

        Args:
            tokens: Number of tokens consumed by the request.
            words: Number of user-facing words generated/submitted.
        """
        update_fields = []
        if tokens > 0:
            self.tokens_used = models.F("tokens_used") + tokens
            update_fields.append("tokens_used")
        if words > 0:
            self.words_used = models.F("words_used") + words
            update_fields.append("words_used")
        if update_fields:
            self.save(update_fields=update_fields)
            self.refresh_from_db(fields=update_fields)
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
