"""
Main project views for frontend pages.
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from accounts.models import User
from experience.models import ExperienceGraph
from jobs.models import JobPosting
from tailoring.models import TailoringSession


def about_view(request):
    """About page view."""
    return render(request, 'about.html')


def login_view(request):
    """Handle user login."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            auth_login(request, user)
            next_url = request.POST.get('next') or 'dashboard'
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'login.html')


def logout_view(request):
    """Handle user logout."""
    auth_logout(request)
    messages.success(request, 'Successfully logged out.')
    return redirect('login')


@login_required
def dashboard(request):
    """Main dashboard view."""
    user = request.user
    
    # Get counts
    experience_count = 0
    try:
        experience_graph = ExperienceGraph.objects.get(user=user)
        experiences = experience_graph.graph_json.get('experiences', [])
        experience_count = len(experiences)
    except ExperienceGraph.DoesNotExist:
        experience_count = 0
    
    job_count = JobPosting.objects.filter(user=user).count()
    tailoring_count = TailoringSession.objects.filter(user=user).count()
    
    # Get recent items
    recent_jobs = JobPosting.objects.filter(user=user).order_by('-created_at')[:5]
    recent_tailoring = TailoringSession.objects.filter(user=user).order_by('-created_at')[:5]
    
    context = {
        'experience_count': experience_count,
        'job_count': job_count,
        'tailoring_count': tailoring_count,
        'recent_jobs': recent_jobs,
        'recent_tailoring': recent_tailoring,
    }
    
    return render(request, 'dashboard.html', context)
