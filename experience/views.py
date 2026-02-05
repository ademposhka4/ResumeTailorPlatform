"""
Experience app views

Views for managing ExperienceGraph.
"""
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import ExperienceGraph
from .serializers import ExperienceGraphSerializer


class ExperienceGraphView(generics.RetrieveUpdateAPIView):
    """
    Retrieve or update the authenticated user's experience graph.
    
    GET /api/experience/ - Get current user's experience graph
    PUT/PATCH /api/experience/ - Update current user's experience graph
    
    Automatically creates an empty graph if one doesn't exist.
    """
    
    serializer_class = ExperienceGraphSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        """
        Get or create the experience graph for the current user.
        """
        obj, created = ExperienceGraph.objects.get_or_create(
            user=self.request.user
        )
        return obj
