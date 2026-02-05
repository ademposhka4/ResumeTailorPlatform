"""
Jobs app views

ViewSet for JobPosting management.
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import JobPosting
from .serializers import JobPostingSerializer


class JobPostingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for JobPosting.
    
    - POST: Create job posting with raw_description or source_url
    - GET: List current user's job postings
    - GET {id}: Retrieve specific job posting
    - PUT/PATCH {id}: Update job posting
    - DELETE {id}: Delete job posting
    """
    
    serializer_class = JobPostingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter to show only current user's job postings.
        Admins can see all postings.
        """
        if self.request.user.role == 'ADMIN':
            return JobPosting.objects.all()
        return JobPosting.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """Automatically set user from request."""
        serializer.save(user=self.request.user)
