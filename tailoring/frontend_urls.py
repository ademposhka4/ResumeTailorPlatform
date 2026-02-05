"""
Frontend URLs for tailoring app.
"""
from django.urls import path
from . import frontend_views

urlpatterns = [
    path('', frontend_views.tailoring_list, name='tailoring_list'),
    path('create/', frontend_views.tailoring_create, name='tailoring_create'),
    path('<int:session_id>/', frontend_views.tailoring_detail, name='tailoring_detail'),
    path('<int:session_id>/delete/', frontend_views.tailoring_delete, name='tailoring_delete'),
]
