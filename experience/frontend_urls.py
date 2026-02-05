"""
Frontend URLs for experience app.
"""
from django.urls import path
from . import frontend_views

app_name = 'experience'

urlpatterns = [
    path('', frontend_views.experience_list, name='list'),
    path('add/', frontend_views.experience_add, name='add'),
    path('edit/<str:experience_id>/', frontend_views.experience_edit, name='edit'),
    path('delete/<str:experience_id>/', frontend_views.experience_delete, name='delete'),
]
