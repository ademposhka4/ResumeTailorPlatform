"""
Experience app URLs
"""
from django.urls import path
from .views import ExperienceGraphView

urlpatterns = [
    path('', ExperienceGraphView.as_view(), name='experience-graph'),
]
