"""
Frontend views for experience management.
Renders HTML pages for user interaction with visual cards.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from .services import ExperienceService


@login_required
def experience_list(request):
    """Display user's experiences as visual cards."""
    experiences = ExperienceService.get_experiences(request.user)
    
    # Color mapping for experience types
    type_colors = {
        'work': 'blue',
        'education': 'purple',
        'project': 'green',
        'volunteer': 'orange'
    }
    
    return render(request, 'experience/list.html', {
        'experiences': experiences,
        'type_colors': type_colors
    })


@login_required
def experience_add(request):
    """Add a new experience."""
    if request.method == 'POST':
        try:
            # Collect form data
            data = {
                'type': request.POST.get('type', ''),
                'title': request.POST.get('title', ''),
                'organization': request.POST.get('organization', ''),
                'location': request.POST.get('location', ''),
                'start_date': request.POST.get('start_date', ''),
                'end_date': request.POST.get('end_date', ''),
                'current': request.POST.get('current') == 'on',
                'description': request.POST.get('description', ''),
                'skills': [s.strip() for s in request.POST.get('skills', '').split(',') if s.strip()],
                'achievements': [a.strip() for a in request.POST.getlist('achievements[]') if a.strip()]
            }
            
            # Add experience
            ExperienceService.add_experience(request.user, data)
            messages.success(request, 'Experience added successfully!')
            return redirect('experience:list')
        
        except ValidationError as e:
            for error in e.messages:
                messages.error(request, error)
            return render(request, 'experience/form.html', {
                'form_data': data,
                'is_edit': False
            })
    
    # GET request
    return render(request, 'experience/form.html', {
        'is_edit': False
    })


@login_required
def experience_edit(request, experience_id):
    """Edit an existing experience."""
    # Get existing experience
    experience = ExperienceService.get_experience_by_id(request.user, experience_id)
    if not experience:
        messages.error(request, 'Experience not found')
        return redirect('experience:list')
    
    if request.method == 'POST':
        try:
            # Collect form data
            data = {
                'type': request.POST.get('type', ''),
                'title': request.POST.get('title', ''),
                'organization': request.POST.get('organization', ''),
                'location': request.POST.get('location', ''),
                'start_date': request.POST.get('start_date', ''),
                'end_date': request.POST.get('end_date', ''),
                'current': request.POST.get('current') == 'on',
                'description': request.POST.get('description', ''),
                'skills': [s.strip() for s in request.POST.get('skills', '').split(',') if s.strip()],
                'achievements': [a.strip() for a in request.POST.getlist('achievements[]') if a.strip()]
            }
            
            # Update experience
            ExperienceService.update_experience(request.user, experience_id, data)
            messages.success(request, 'Experience updated successfully!')
            return redirect('experience:list')
        
        except ValidationError as e:
            for error in e.messages:
                messages.error(request, error)
            return render(request, 'experience/form.html', {
                'form_data': data,
                'experience_id': experience_id,
                'is_edit': True
            })
    
    # GET request - populate form with existing data
    return render(request, 'experience/form.html', {
        'form_data': experience,
        'experience_id': experience_id,
        'is_edit': True
    })


@login_required
def experience_delete(request, experience_id):
    """Delete an experience."""
    if request.method == 'POST':
        if ExperienceService.delete_experience(request.user, experience_id):
            messages.success(request, 'Experience deleted successfully!')
        else:
            messages.error(request, 'Experience not found')
    
    return redirect('experience:list')
