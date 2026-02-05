"""
Tailoring app views

ViewSet for TailoringSession with AI workflow integration.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.utils import check_and_increment_tokens
from experience.models import ExperienceGraph
from jobs.models import JobPosting

from .models import TailoringSession
from .serializers import TailoringSessionSerializer, TailoringSessionCreateSerializer
from .services import AgentKitTailoringService


class TailoringSessionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for TailoringSession.
    
    - POST: Create new tailoring session with job_id
    - GET: List current user's sessions
    - GET {id}: Retrieve specific session
    - POST {id}/restart/: Clone and re-run a session
    """
    
    serializer_class = TailoringSessionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter to show only current user's tailoring sessions.
        Admins can see all sessions.
        """
        if self.request.user.role == 'ADMIN':
            return TailoringSession.objects.all()
        return TailoringSession.objects.filter(user=self.request.user)
    
    def create(self, request, *args, **kwargs):
        """
        Create a new tailoring session.
        
        Flow:
        1. Validate job_id
        2. Check token quota
        3. Load user's experience graph
        4. Call AgentKit service
        5. Save results
        6. Increment tokens
        """
        # Validate input
        create_serializer = TailoringSessionCreateSerializer(data=request.data)
        create_serializer.is_valid(raise_exception=True)

        job_id = create_serializer.validated_data['job_id']
        user_parameter_input = create_serializer.validated_data.get('parameters') or {}

        # Get job posting
        job = get_object_or_404(JobPosting, id=job_id, user=request.user)
        
        # Check token quota (estimate 1 token per request)
        # TODO: Adjust cost based on actual token usage from OpenAI
        try:
            check_and_increment_tokens(request.user, cost=1)
        except PermissionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Load user's experience graph
        try:
            experience_graph = ExperienceGraph.objects.get(user=request.user)
            experience_data = experience_graph.graph_json
        except ExperienceGraph.DoesNotExist:
            return Response(
                {'error': 'Experience graph not found. Please create your experience profile first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create session
        session = TailoringSession.objects.create(
            user=request.user,
            job=job,
            input_experience_snapshot=experience_data,
            parameters=user_parameter_input,
            status='PROCESSING',
        )

        # Call AgentKit service
        try:
            service = AgentKitTailoringService()

            # Use raw_description if available; OpenAI will fetch from URL via grounding
            job_description = job.raw_description or ""
            source_url = job.source_url or ""

            normalized_parameters = service.normalize_parameters(user_parameter_input or {})

            result = service.run_workflow(
                job_description=job_description,
                experience_graph=experience_data,
                parameters=normalized_parameters,
                source_url=source_url
            )

            token_usage = result.get("token_usage", {})
            words_generated = result.get("words_generated", 0)
            if words_generated:
                token_usage = {**token_usage, "words_generated": words_generated}

            session.generated_title = result.get('title', '')
            session.generated_bullets = result.get('bullets', [])
            session.generated_sections = result.get('sections', [])
            session.tailored_resume = result.get('summary', '')

            ats_score = result.get("ats_score", {})
            suggestions = result.get("suggestions", [])
            if ats_score:
                ats_summary = (
                    f"📊 ATS Compatibility: {ats_score.get('overall_score', 0)}% | "
                    f"Required Skills: {ats_score.get('required_skills_match', 0)}% | "
                    f"Keywords: {ats_score.get('keyword_match', 0)}%"
                )
                suggestions = [ats_summary] + suggestions

            guardrail_report = result.get("guardrail_report", [])
            cover_letter_points = result.get("cover_letter_talking_points", [])

            session.ai_suggestions = "\n".join(suggestions)
            session.cover_letter = result.get('cover_letter', '')
            session.token_usage = token_usage
            session.openai_run_id = result.get('run_id', '')
            session.parameters = normalized_parameters
            session.output_metadata = {
                "bullet_details": result.get("bullet_details", []),
                "guardrails": guardrail_report,
                "bullet_quality": result.get("bullet_quality", {}),
                "section_layout": result.get("section_layout", []),
                "cover_letter_talking_points": cover_letter_points,
            }
            session.status = TailoringSession.Status.COMPLETED
            session.completed_at = timezone.now()
            session.save(
                update_fields=[
                    "generated_title",
                    "generated_bullets",
                    "generated_sections",
                    "tailored_resume",
                    "ai_suggestions",
                    "cover_letter",
                    "token_usage",
                    "openai_run_id",
                    "parameters",
                    "output_metadata",
                    "status",
                    "completed_at",
                    "updated_at",
                ]
            )

        except NotImplementedError:
            # Service not yet implemented
            session.status = 'FAILED'
            session.save()
            return Response(
                {
                    'error': 'AI tailoring service not yet implemented.',
                    'session_id': session.id,
                    'message': 'Session created but AI workflow needs implementation in tailoring/services.py'
                },
                status=status.HTTP_501_NOT_IMPLEMENTED
            )
        except Exception as e:
            # Handle other errors
            session.status = 'FAILED'
            session.save()
            return Response(
                {'error': f'Tailoring failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Return completed session
        serializer = self.get_serializer(session)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def restart(self, request, pk=None):
        """
        Restart a tailoring session.
        
        POST /api/tailoring/{id}/restart/
        
        Creates a new session with the same job and current experience graph.
        """
        # Get original session
        original_session = self.get_object()
        
        # Check token quota
        try:
            check_and_increment_tokens(request.user, cost=1)
        except PermissionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get current experience graph
        try:
            experience_graph = ExperienceGraph.objects.get(user=request.user)
            experience_data = experience_graph.graph_json
        except ExperienceGraph.DoesNotExist:
            return Response(
                {'error': 'Experience graph not found.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create new session
        new_session = TailoringSession.objects.create(
            user=request.user,
            job=original_session.job,
            input_experience_snapshot=experience_data,
            parameters=original_session.parameters,
            status='PROCESSING',
        )

        # Call AgentKit service
        try:
            service = AgentKitTailoringService()
            job = original_session.job

            # Use raw_description if available; OpenAI will fetch from URL via grounding
            job_description = job.raw_description or ""
            source_url = job.source_url or ""

            normalized_parameters = service.normalize_parameters(original_session.parameters or {})

            result = service.run_workflow(
                job_description=job_description,
                experience_graph=experience_data,
                parameters=normalized_parameters,
                source_url=source_url
            )

            token_usage = result.get("token_usage", {})
            words_generated = result.get("words_generated", 0)
            if words_generated:
                token_usage = {**token_usage, "words_generated": words_generated}

            new_session.generated_title = result.get('title', '')
            new_session.generated_bullets = result.get('bullets', [])
            new_session.generated_sections = result.get('sections', [])
            new_session.tailored_resume = result.get('summary', '')

            ats_score = result.get("ats_score", {})
            suggestions = result.get('suggestions', [])
            if ats_score:
                ats_summary = (
                    f"📊 ATS Compatibility: {ats_score.get('overall_score', 0)}% | "
                    f"Required Skills: {ats_score.get('required_skills_match', 0)}% | "
                    f"Keywords: {ats_score.get('keyword_match', 0)}%"
                )
                suggestions = [ats_summary] + suggestions

            guardrail_report = result.get('guardrail_report', [])
            cover_letter_points = result.get("cover_letter_talking_points", [])

            new_session.ai_suggestions = "\n".join(suggestions)
            new_session.cover_letter = result.get('cover_letter', '')
            new_session.token_usage = token_usage
            new_session.openai_run_id = result.get('run_id', '')
            new_session.parameters = normalized_parameters
            new_session.output_metadata = {
                "bullet_details": result.get("bullet_details", []),
                "guardrails": guardrail_report,
                "bullet_quality": result.get("bullet_quality", {}),
                "section_layout": result.get("section_layout", []),
                "cover_letter_talking_points": cover_letter_points,
            }
            new_session.status = TailoringSession.Status.COMPLETED
            new_session.completed_at = timezone.now()
            new_session.save(
                update_fields=[
                    "generated_title",
                    "generated_bullets",
                    "generated_sections",
                    "tailored_resume",
                    "ai_suggestions",
                    "cover_letter",
                    "token_usage",
                    "openai_run_id",
                    "parameters",
                    "output_metadata",
                    "status",
                    "completed_at",
                    "updated_at",
                ]
            )

        except NotImplementedError:
            new_session.status = 'FAILED'
            new_session.save()
            return Response(
                {
                    'error': 'AI tailoring service not yet implemented.',
                    'session_id': new_session.id,
                },
                status=status.HTTP_501_NOT_IMPLEMENTED
            )
        except Exception as e:
            new_session.status = 'FAILED'
            new_session.save()
            return Response(
                {'error': f'Tailoring failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        serializer = self.get_serializer(new_session)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
