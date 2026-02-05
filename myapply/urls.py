"""
URL configuration for myapply project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from accounts.views import UserViewSet
from profiles.views import JobSeekerProfileViewSet
from jobs.views import JobPostingViewSet
from tailoring.views import TailoringSessionViewSet
from myapply.views import login_view, logout_view, dashboard, about_view

# Create router and register viewsets
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'profiles', JobSeekerProfileViewSet, basename='profile')
router.register(r'jobs', JobPostingViewSet, basename='job')
router.register(r'tailoring', TailoringSessionViewSet, basename='tailoring')

urlpatterns = [
    # Frontend views
    path('', dashboard, name='dashboard'),
    path('about/', about_view, name='about'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('experience/', include('experience.frontend_urls')),
    path('jobs/', include('jobs.frontend_urls')),
    path('tailoring/', include('tailoring.frontend_urls')),
    path('profile/', include('profiles.frontend_urls')),
    path('accounts/', include('accounts.urls')),
    
    # API views
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/experience/', include('experience.urls')),
    path('api/maps/', include('maps.urls')),
    path('api-auth/', include('rest_framework.urls')),
]
