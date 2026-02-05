"""
Accounts app views

ViewSet and endpoints for user management and authentication.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from .models import User
from .serializers import UserSerializer
from .permissions import IsAdminOrSelf
from django.shortcuts import render, redirect
from .forms import CustomUserCreationForm
from django.contrib import messages

class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for User management.
    
    - List/create: Staff/admin only
    - Retrieve/update/delete: Admin or self only
    - Special 'me' endpoint for current user
    """
    
    queryset = User.objects.all()
    serializer_class = UserSerializer
    
    def get_permissions(self):
        """
        Instantiate and return the list of permissions that this view requires.
        """
        if self.action in ['list', 'create']:
            permission_classes = [IsAdminUser]
        elif self.action == 'me':
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAdminOrSelf]
        return [permission() for permission in permission_classes]
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """
        Return the current authenticated user's data.
        
        GET /api/users/me/
        """
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


def signup(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Account created successfully! Please log in.")
            return redirect("login")  # adjust if your login view is elsewhere
    else:
        form = CustomUserCreationForm()

    # Pass the form directly
    return render(request, "accounts/signup.html", {"form": form})
