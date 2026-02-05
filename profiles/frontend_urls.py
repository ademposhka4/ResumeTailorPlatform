"""
Frontend URLs for profiles app.
"""
from django.urls import path
from . import frontend_views

urlpatterns = [
    path('', frontend_views.profile_view, name='profile_view'),
    path('edit/', frontend_views.profile_edit, name='profile_edit'),
]
