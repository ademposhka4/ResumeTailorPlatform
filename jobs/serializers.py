"""
Jobs app serializers

Serializers for JobPosting model.
"""
from rest_framework import serializers
from .models import JobPosting


class JobPostingSerializer(serializers.ModelSerializer):
    """
    Serializer for JobPosting.
    
    Accepts either raw_description or source_url (or both).
    User is automatically set from request context.
    """
    
    username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = JobPosting
        fields = [
            'id',
            'user',
            'username',
            'title',
            'company',
            'source_url',
            'raw_description',
            'location_text',
            'parsed_requirements',
            'metadata',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'user',
            'created_at',
            'updated_at',
            'parsed_requirements',
            'metadata',
        ]

    def validate(self, attrs):
        """
        Ensure at least one source of job information is provided.
        """
        raw_description = attrs.get('raw_description')
        source_url = attrs.get('source_url')

        # When updating, fall back to existing values if not supplied
        if self.instance:
            raw_description = raw_description if raw_description is not None else self.instance.raw_description
            source_url = source_url if source_url is not None else self.instance.source_url

        if not raw_description and not source_url:
            raise serializers.ValidationError(
                'Provide either a job description, a job URL, or both.'
            )

        return attrs
