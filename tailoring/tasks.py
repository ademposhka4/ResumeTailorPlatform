"""
Background tasks for the tailoring app using Django-Q.
"""
import json
import logging
import traceback
from typing import List

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from experience.models import ExperienceGraph
from .models import TailoringSession
from .services import AgentKitTailoringService, TailoringPipelineError

logger = logging.getLogger(__name__)


def _format_debug_entries(entries: List[str]) -> str:
    """
    Join debug entries into a newline separated string.
    """
    return "\n".join(entries)


def process_tailoring_session(session_id: int) -> None:
    """
    Background task that orchestrates a tailoring session.
    
    This task is idempotent and safe to re-run while a session is pending.
    Can be called directly or queued via Django-Q's async_task().
    """
    debug_entries: List[str] = []

    def log_debug(message: str) -> None:
        timestamp = timezone.now().isoformat()
        entry = f"[{timestamp}] {message}"
        debug_entries.append(entry)
        logger.info("Tailoring session %s: %s", session_id, message)

    try:
        with transaction.atomic():
            session = (
                TailoringSession.objects.select_for_update()
                .select_related("user", "job")
                .get(id=session_id)
            )

            if session.status == TailoringSession.Status.PROCESSING:
                log_debug("Session already processing; skipping duplicate task.")
                return

            if session.status == TailoringSession.Status.COMPLETED:
                log_debug("Session already completed; no action required.")
                return

            session.status = TailoringSession.Status.PROCESSING
            session.error_message = ""
            session.completed_at = None
            session.save(update_fields=["status", "error_message", "completed_at", "updated_at"])

        service = AgentKitTailoringService()
        job = session.job
        user: User = session.user

        log_debug("Starting tailoring pipeline.")

        existing_job_snapshot = session.job_snapshot or {}
        raw_description = job.raw_description or existing_job_snapshot.get("raw_description", "")
        source_url = job.source_url or existing_job_snapshot.get("source_url", "")

        # OpenAI will use web search (grounding) to fetch job details from URL
        if source_url:
            log_debug(f"Will use OpenAI web search for job URL: {source_url}")

        job_snapshot = {
            "title": job.title,
            "company": job.company,
            "location_text": job.location_text,
            "source_url": source_url,
            "raw_description": raw_description,
        }
        job_snapshot.update(existing_job_snapshot)

        experience_snapshot = session.input_experience_snapshot or {}
        if not experience_snapshot:
            try:
                experience_snapshot = ExperienceGraph.objects.get(user=user).graph_json
                log_debug("Captured experience graph snapshot from database.")
            except ExperienceGraph.DoesNotExist:
                experience_snapshot = {}
                log_debug("No experience graph found for user; proceeding with empty data.")

        # Use raw description as-is; OpenAI will fetch from URL if provided
        merged_job_description = raw_description or ""
        if not merged_job_description.strip() and not source_url:
            raise TailoringPipelineError(
                "No job description or URL provided. Unable to tailor resume content."
            )
        if not merged_job_description.strip():
            log_debug("No description text; relying on OpenAI web search from URL")

        parameters = service.normalize_parameters(session.parameters or {})

        log_debug(f"Using tailoring parameters: {json.dumps(parameters)}")

        result = service.run_workflow(
            merged_job_description,
            experience_snapshot,
            parameters=parameters,
            source_url=source_url,
        )

        token_usage = result.get("token_usage", {})
        words_generated = result.get("words_generated", 0)
        if words_generated:
            token_usage = {**token_usage, "words_generated": words_generated}

        session.generated_title = result.get("title", "")
        session.generated_bullets = result.get("bullets", [])
        session.generated_sections = result.get("sections", [])
        session.tailored_resume = result.get("summary", "")
        
        # Include ATS score in suggestions
        ats_score = result.get("ats_score", {})
        suggestions = result.get("suggestions", [])
        
        # Prepend ATS score summary to suggestions
        if ats_score:
            ats_summary = (
                f"📊 ATS Compatibility: {ats_score.get('overall_score', 0)}% | "
                f"Required Skills: {ats_score.get('required_skills_match', 0)}% | "
                f"Keywords: {ats_score.get('keyword_match', 0)}%"
            )
            suggestions = [ats_summary] + suggestions
            log_debug(f"ATS Score: {ats_score.get('overall_score', 0)}%")

        guardrail_report = result.get("guardrail_report", [])
        if guardrail_report:
            log_debug(f"Guardrail findings: {json.dumps(guardrail_report)}")

        cover_letter_points = result.get("cover_letter_talking_points", [])
        if cover_letter_points:
            log_debug(
                "Cover letter talking points prepared: "
                f"{', '.join(cover_letter_points[:3])}"
            )

        session.ai_suggestions = "\n".join(suggestions)
        session.cover_letter = result.get("cover_letter", "")
        session.token_usage = token_usage
        session.openai_run_id = result.get("run_id", "")
        session.job_snapshot = job_snapshot
        session.input_experience_snapshot = experience_snapshot
        session.parameters = parameters
        session.output_metadata = {
            "bullet_details": result.get("bullet_details", []),
            "guardrails": guardrail_report,
            "bullet_quality": result.get("bullet_quality", {}),
            "section_layout": result.get("section_layout", []),
            "cover_letter_talking_points": cover_letter_points,
            "job_location_name": result.get("job_location_name", ""),
            "job_location_coordinates": result.get("job_location_coordinates"),
        }
        session.status = TailoringSession.Status.COMPLETED
        session.completed_at = timezone.now()

        debug_payload = result.get("debug", {})
        if debug_payload:
            log_debug(f"Pipeline debug data: {json.dumps(debug_payload)}")
        
        # Log bullet quality issues if any
        bullet_quality = result.get("bullet_quality", {})
        if bullet_quality.get("issues_found", 0) > 0:
            log_debug(
                f"Found {bullet_quality['issues_found']} bullet points with quality issues"
            )

        log_debug("Tailoring pipeline completed successfully.")

        session.debug_log = _format_debug_entries(debug_entries)
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
                "job_snapshot",
                "input_experience_snapshot",
                "parameters",
                "output_metadata",
                "status",
                "completed_at",
                "debug_log",
                "updated_at",
            ]
        )

        # Record token usage for the user
        # Use actual OpenAI token counts for accurate billing
        prompt_tokens = token_usage.get("prompt_tokens", 0)
        completion_tokens = token_usage.get("completion_tokens", 0)
        total_tokens = token_usage.get("total_tokens", 0)
        
        # Fallback calculation if total not provided
        if not total_tokens and (prompt_tokens or completion_tokens):
            total_tokens = prompt_tokens + completion_tokens
        
        # Ensure we have valid positive numbers
        total_tokens = max(0, total_tokens)
        words_generated = max(0, words_generated)
        
        log_debug(
            f"Recording usage: {total_tokens} tokens "
            f"({prompt_tokens} prompt + {completion_tokens} completion), "
            f"{words_generated} words"
        )
        
        user.record_usage(
            tokens=total_tokens,
            words=words_generated,
        )

    except TailoringPipelineError as exc:
        log_debug(f"Pipeline error: {exc}")
        with transaction.atomic():
            try:
                session = TailoringSession.objects.select_for_update().get(id=session_id)
                session.status = TailoringSession.Status.FAILED
                session.error_message = str(exc)
                session.debug_log = _format_debug_entries(debug_entries)
                session.save(update_fields=["status", "error_message", "debug_log", "updated_at"])
            except TailoringSession.DoesNotExist:
                log_debug("Tailoring session disappeared during failure handling.")
        return
    except TailoringSession.DoesNotExist:
        log_debug("Tailoring session not found; aborting task.")
        return
    except Exception as exc:  # noqa: BLE001
        traceback_str = traceback.format_exc()
        log_debug(f"Unexpected error: {exc}")

        # Mark session as failed and save debug info
        # Django-Q will handle retries automatically based on Q_CLUSTER settings
        with transaction.atomic():
            try:
                session = TailoringSession.objects.select_for_update().get(id=session_id)
                session.status = TailoringSession.Status.FAILED
                session.error_message = f"Unexpected error: {exc}"
                session.debug_log = _format_debug_entries(debug_entries + [traceback_str])
                session.save(update_fields=["status", "error_message", "debug_log", "updated_at"])
            except TailoringSession.DoesNotExist:
                log_debug("Session missing during failure handling.")
        
        # Re-raise to let Django-Q know the task failed
        raise
