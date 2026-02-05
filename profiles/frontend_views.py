"""
Frontend views for profiles app.
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import JobSeekerProfile


@login_required
def profile_view(request):
    """Display user's profile."""
    try:
        profile = JobSeekerProfile.objects.get(user=request.user)
    except JobSeekerProfile.DoesNotExist:
        profile = None
    
    context = {'profile': profile}
    return render(request, 'profiles/view.html', context)


@login_required
def profile_edit(request):
    """Edit user's profile."""
    try:
        profile = JobSeekerProfile.objects.get(user=request.user)
    except JobSeekerProfile.DoesNotExist:
        profile = None
    
    if request.method == 'POST':
        location = request.POST.get('location', '')
        preferred_radius_km = request.POST.get('preferred_radius_km', 30)
        
        try:
            preferred_radius_km = int(preferred_radius_km)
        except ValueError:
            preferred_radius_km = 30
        
        if profile:
            profile.location = location
            profile.preferred_radius_km = preferred_radius_km
            profile.save()
            messages.success(request, 'Profile updated successfully.')
        else:
            profile = JobSeekerProfile.objects.create(
                user=request.user,
                location=location,
                preferred_radius_km=preferred_radius_km
            )
            messages.success(request, 'Profile created successfully.')
        
        return redirect('profile_view')
    
    context = {'profile': profile}
    return render(request, 'profiles/edit.html', context)
