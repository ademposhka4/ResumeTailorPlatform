"""
Frontend URLs for jobs app.
"""
from django.urls import path
from . import frontend_views

urlpatterns = [
    path('', frontend_views.job_list, name='job_list'),
    path('create/', frontend_views.job_create, name='job_create'),
    path('<int:job_id>/', frontend_views.job_detail, name='job_detail'),
    path('<int:job_id>/edit/', frontend_views.job_edit, name='job_edit'),
    path('<int:job_id>/delete/', frontend_views.job_delete, name='job_delete'),
]
