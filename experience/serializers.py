"""
Experience app serializers

Serializers for ExperienceGraph model.
"""
from rest_framework import serializers
from .models import ExperienceGraph


class ExperienceGraphSerializer(serializers.ModelSerializer):
    """
    Serializer for ExperienceGraph.
    
    Exposes the graph_json field for storing structured experience data.
    User is read-only and automatically set from request context.
    """
    
    username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = ExperienceGraph
        fields = [
            'id',
            'user',
            'username',
            'graph_json',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'updated_at']
