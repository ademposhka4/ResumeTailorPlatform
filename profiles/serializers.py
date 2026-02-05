"""
Profiles app serializers

Serializers for JobSeekerProfile model.
"""
from rest_framework import serializers
from .models import JobSeekerProfile


class JobSeekerProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for JobSeekerProfile.
    
    Exposes profile fields including location and radius preferences.
    User is read-only and automatically set from request context.
    """
    
    username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = JobSeekerProfile
        fields = [
            'id',
            'user',
            'username',
            'location',
            'preferred_radius_km',
            'default_resume_url',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']
