"""
Accounts app permissions

Custom permissions for role-based access control.
"""
from rest_framework import permissions


class IsAdminOrSelf(permissions.BasePermission):
    """
    Permission that allows:
    - Admins to access any user
    - Users to access only their own data
    """
    
    def has_object_permission(self, request, view, obj):
        # Admin users can access anything
        if request.user.role == 'ADMIN':
            return True
        
        # Users can only access their own data
        return obj == request.user
