"""
Tailoring app serializers

Serializers for TailoringSession model.
"""
from rest_framework import serializers
from .models import TailoringSession


class TailoringSessionSerializer(serializers.ModelSerializer):
    """
    Serializer for TailoringSession.
    
    Exposes all session data including AI-generated outputs.
    """
    
    username = serializers.CharField(source='user.username', read_only=True)
    job_title = serializers.CharField(source='job.title', read_only=True)
    job_company = serializers.CharField(source='job.company', read_only=True)
    cover_letter_talking_points = serializers.SerializerMethodField()
    guardrail_report = serializers.SerializerMethodField()
    section_layout = serializers.SerializerMethodField()
    bullet_details = serializers.SerializerMethodField()
    
    class Meta:
        model = TailoringSession
        fields = [
            'id',
            'user',
            'username',
            'job',
            'job_title',
            'job_company',
            'input_experience_snapshot',
            'generated_title',
            'generated_bullets',
            'generated_sections',
            'tailored_resume',
            'cover_letter',
            'cover_letter_talking_points',
            'ai_suggestions',
            'token_usage',
            'output_metadata',
            'guardrail_report',
            'section_layout',
            'bullet_details',
            'parameters',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'user',
            'input_experience_snapshot',
            'generated_title',
            'generated_bullets',
            'generated_sections',
            'tailored_resume',
            'cover_letter',
            'ai_suggestions',
            'token_usage',
            'output_metadata',
            'parameters',
            'status',
            'created_at',
            'updated_at',
        ]

    def get_cover_letter_talking_points(self, obj: TailoringSession) -> list:
        metadata = obj.output_metadata or {}
        return metadata.get('cover_letter_talking_points', [])

    def get_guardrail_report(self, obj: TailoringSession) -> list:
        metadata = obj.output_metadata or {}
        return metadata.get('guardrails', [])

    def get_section_layout(self, obj: TailoringSession) -> list:
        metadata = obj.output_metadata or {}
        layout = metadata.get('section_layout')
        if layout:
            return layout
        return obj.parameters.get('section_layout', []) if isinstance(obj.parameters, dict) else []

    def get_bullet_details(self, obj: TailoringSession) -> list:
        metadata = obj.output_metadata or {}
        return metadata.get('bullet_details', [])


class TailoringSessionCreateSerializer(serializers.Serializer):
    """
    Serializer for creating a new tailoring session.
    
    Only requires job_id; everything else is derived.
    """
    
    job_id = serializers.IntegerField()
    parameters = serializers.JSONField(required=False)
