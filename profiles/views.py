"""
Profiles app views

ViewSet for JobSeekerProfile management.
"""
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import JobSeekerProfile
from .serializers import JobSeekerProfileSerializer


class JobSeekerProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet for JobSeekerProfile.
    
    - Users can CRUD their own profile
    - Admins can list all profiles
    - Automatically creates profile if it doesn't exist
    """
    
    serializer_class = JobSeekerProfileSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter queryset based on user role.
        - Admins see all profiles
        - Users see only their own profile
        """
        if self.request.user.role == 'ADMIN':
            return JobSeekerProfile.objects.all()
        return JobSeekerProfile.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """Automatically set user from request."""
        serializer.save(user=self.request.user)
    
    def list(self, request, *args, **kwargs):
        """
        List profiles. For non-admin users, return their profile or empty list.
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
