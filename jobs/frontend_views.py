"""
Frontend views for jobs app.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import JobPosting


@login_required
def job_list(request):
    """List all jobs for the user with tailoring session data."""
    from django.db.models import Count, Prefetch
    from tailoring.models import TailoringSession

    jobs = JobPosting.objects.filter(user=request.user)\
        .prefetch_related(
            Prefetch(
                'tailoring_sessions',
                queryset=TailoringSession.objects.order_by('-created_at')
            )
        )\
        .annotate(session_count=Count('tailoring_sessions'))\
        .order_by('-created_at')

    context = {'jobs': jobs}
    return render(request, 'jobs/list.html', context)


@login_required
def job_detail(request, job_id):
    """Display job details with tailoring sessions."""
    from django.db.models import Prefetch
    from tailoring.models import TailoringSession

    job = get_object_or_404(
        JobPosting.objects.prefetch_related(
            Prefetch(
                'tailoring_sessions',
                queryset=TailoringSession.objects.order_by('-created_at')
            )
        ),
        id=job_id,
        user=request.user
    )

    tailoring_stats = job.get_tailoring_stats()
    context = {
        'job': job,
        'tailoring_stats': tailoring_stats
    }
    return render(request, 'jobs/detail.html', context)


@login_required
def job_create(request):
    """Create a new job posting."""
    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        company = (request.POST.get('company') or '').strip()
        raw_description = (request.POST.get('raw_description') or '').strip()
        location_text = (request.POST.get('location_text') or '').strip()
        source_url = (request.POST.get('source_url') or '').strip()

        if not title or not company:
            messages.error(request, 'Title and company are required.')
            return redirect('job_create')

        if not raw_description and not source_url:
            messages.error(
                request,
                'Provide either a job description, a job URL, or both.'
            )
            return redirect('job_create')

        job = JobPosting.objects.create(
            user=request.user,
            title=title,
            company=company,
            raw_description=raw_description,
            location_text=location_text,
            source_url=source_url,
        )
        messages.success(request, f'Job "{title}" created successfully.')
        return redirect('job_detail', job_id=job.id)

    return render(request, 'jobs/create.html')


@login_required
def job_edit(request, job_id):
    """Edit an existing job posting."""
    job = get_object_or_404(JobPosting, id=job_id, user=request.user)
    
    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        company = (request.POST.get('company') or '').strip()
        raw_description = (request.POST.get('raw_description') or '').strip()
        location_text = (request.POST.get('location_text') or '').strip()
        source_url = (request.POST.get('source_url') or '').strip()

        if not title or not company:
            messages.error(request, 'Title and company are required.')
            return redirect('job_edit', job_id=job.id)

        if not raw_description and not source_url:
            messages.error(
                request,
                'Provide either a job description, a job URL, or both.'
            )
            return redirect('job_edit', job_id=job.id)

        job.title = title
        job.company = company
        job.raw_description = raw_description
        job.location_text = location_text
        job.source_url = source_url
        job.save()

        messages.success(request, f'Job "{job.title}" updated successfully.')
        return redirect('job_detail', job_id=job.id)
    
    context = {'job': job}
    return render(request, 'jobs/edit.html', context)


@login_required
def job_delete(request, job_id):
    """Delete a job posting."""
    job = get_object_or_404(JobPosting, id=job_id, user=request.user)
    
    if request.method == 'POST':
        title = job.title
        job.delete()
        messages.success(request, f'Job "{title}" deleted successfully.')
        return redirect('job_list')
    
    context = {'job': job}
    return render(request, 'jobs/delete.html', context)
