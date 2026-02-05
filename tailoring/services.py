"""
Tailoring app services

Core service for AI-powered resume tailoring using OpenAI Responses API.
This module orchestrates:
- Job requirement extraction and profiling
- Experience graph scoring and snippet selection
- OpenAI API calls with conditional JSON mode and web search
- Guardrail validation and bullet regeneration
- ATS scoring and quality validation

Designed to work with Django-Q for asynchronous task processing.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from django.conf import settings

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled gracefully during runtime
    OpenAI = None

logger = logging.getLogger(__name__)


STOPWORDS = {
    "and",
    "the",
    "to",
    "of",
    "a",
    "for",
    "in",
    "on",
    "with",
    "an",
    "by",
    "is",
    "be",
    "as",
    "or",
    "at",
    "from",
    "into",
    "will",
    "that",
}


class TailoringPipelineError(Exception):
    """
    Domain-specific exception for tailoring failures.
    """


@dataclass
class TailoringResult:
    """
    Structured representation of the OpenAI response payloads.
    """

    title: str = ""
    sections: List[Dict[str, List[str]]] = field(default_factory=list)
    bullets: List[str] = field(default_factory=list)
    bullet_details: List[Dict[str, object]] = field(default_factory=list)
    summary: str = ""
    suggestions: List[str] = field(default_factory=list)
    cover_letter: str = ""
    cover_letter_talking_points: List[str] = field(default_factory=list)
    token_usage: Dict[str, int] = field(default_factory=dict)
    run_id: str = ""
    guardrail_report: List[Dict[str, object]] = field(default_factory=list)
    debug: Dict[str, object] = field(default_factory=dict)
    job_location_name: str = ""
    job_location_coordinates: Optional[Dict[str, float]] = None

    @property
    def words_generated(self) -> int:
        """
        Count approximate number of words produced for usage reporting.
        """
        text_fragments = self.bullets[:]
        if self.summary:
            text_fragments.append(self.summary)
        if self.cover_letter:
            text_fragments.append(self.cover_letter)
        text = " ".join(text_fragments)
        return len(re.findall(r"\w+", text))


@dataclass
class JobProfile:
    """
    Structured view of job requirements for prompt construction.
    """

    source_url: str
    description: str
    requirements: Dict[str, List[str]]
    requirement_buckets: Dict[str, List[str]]
    location_name: str = ""
    location_coordinates: Optional[Dict[str, float]] = None  # {"lat": float, "lon": float}

    def to_prompt_dict(self) -> Dict[str, object]:
        return {
            "source_url": self.source_url,
            "summary": self.description[:1200],
            "requirements": self.requirements,
            "buckets": self.requirement_buckets,
            "location": self.location_name,
        }


@dataclass
class ExperienceSnippet:
    """
    Experience graph entry distilled for prompt usage.
    """

    snippet_id: str
    bucket: str
    title: str
    organization: str
    time_frame: str
    summary: str
    achievements: List[str]
    skills: List[str]
    source_ref: Dict[str, object]

    def to_prompt_dict(self) -> Dict[str, object]:
        return {
            "id": self.snippet_id,
            "bucket": self.bucket,
            "title": self.title,
            "organization": self.organization,
            "time_frame": self.time_frame,
            "summary": self.summary,
            "achievements": self.achievements,
            "skills": self.skills,
        }


@dataclass
class GuardrailFinding:
    """
    Result from guardrail validation against stretch policy.
    """

    snippet_id: str
    bullet_id: str
    status: str
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "snippet_id": self.snippet_id,
            "bullet_id": self.bullet_id,
            "status": self.status,
            "reasons": self.reasons,
        }


class AgentKitTailoringService:
    """
    Service for AI-powered resume tailoring using the OpenAI Responses API.
    """

    DEFAULT_PARAMETERS = {
        "sections": [
            "Professional Experience",
            "Leadership",
            "Projects",
        ],
        "bullets_per_section": 3,
        "tone": "confident and metric-driven",
        "include_summary": True,
        "include_cover_letter": False,
        "temperature": 0.35,
        "max_output_tokens": 3500,  # Increased to prevent JSON truncation with job_requirements and web search content
        "stretch_level": 2,
        "section_layout": [
            "Professional Experience",
            "Leadership",
            "Projects",
        ],
        "cover_letter_inserts": [],
    }

    SECTION_BUCKET_ALIASES = {
        "professional": "Professional Experience",
        "leadership": "Leadership",
        "projects": "Projects",
        "skills": "Skills & Tools",
    }

    MAX_SNIPPETS_PER_BUCKET = 3

    STRETCH_LEVEL_DESCRIPTORS = {
        0: "Exact: No embellishment. Only rephrase provided facts.",
        1: "Conservative: Allow mild reframing but stay literal to provided facts.",
        2: "Balanced: Blend facts with light amplification (≤10% metric lift).",
        3: "Aggressive: Allow up to 20% amplification and reordering for impact.",
    }

    TECH_KEYWORDS = {
        # Programming Languages
        "python", "java", "javascript", "typescript", "c++", "c#", "ruby", "php", "swift",
        "kotlin", "go", "rust", "scala", "r", "matlab", "perl", "vb.net", "objective-c",
        # Databases
        "sql", "nosql", "mysql", "postgresql", "mongodb", "redis", "cassandra", "dynamodb",
        "oracle", "sqlserver", "mariadb", "sqlite", "elasticsearch", "neo4j", "couchdb",
        # Cloud Platforms
        "aws", "azure", "gcp", "heroku", "digitalocean", "linode", "cloudflare",
        "s3", "ec2", "lambda", "cloudformation", "cloudwatch", "rds", "sagemaker",
        # Frameworks & Libraries
        "react", "angular", "vue", "django", "flask", "fastapi", "spring", "express",
        "node.js", "nodejs", ".net", "asp.net", "rails", "laravel", "next.js", "gatsby",
        # DevOps & Tools
        "docker", "kubernetes", "terraform", "ansible", "jenkins", "gitlab", "github",
        "ci/cd", "git", "linux", "unix", "bash", "powershell", "nginx", "apache",
        # Data & Analytics
        "spark", "hadoop", "kafka", "airflow", "databricks", "snowflake", "redshift",
        "tableau", "powerbi", "looker", "qlik", "pandas", "numpy", "scipy",
        # AI/ML
        "ml", "ai", "tensorflow", "pytorch", "scikit-learn", "keras", "transformers",
        "nlp", "computer vision", "deep learning", "machine learning", "data science",
        # Methodologies
        "agile", "scrum", "kanban", "waterfall", "devops", "tdd", "bdd", "pair programming",
        # Business Tools
        "salesforce", "sap", "oracle", "workday", "servicenow", "jira", "confluence",
        "slack", "microsoft teams", "sharepoint", "excel", "powerpoint",
        # Other
        "api", "rest", "graphql", "microservices", "serverless", "etl", "data pipeline",
        "html", "css", "sass", "webpack", "babel", "typescript", "json", "xml", "yaml",
        "oauth", "jwt", "saml", "sso", "encryption", "security", "compliance", "gdpr",
    }
    
    # ATS-critical action verbs that show impact
    ATS_ACTION_VERBS = {
        # Leadership & Management
        "led", "managed", "directed", "supervised", "coordinated", "oversaw", "mentored",
        "coached", "trained", "guided", "delegated", "organized", "facilitated",
        # Achievement & Results
        "achieved", "improved", "increased", "decreased", "reduced", "accelerated",
        "optimized", "streamlined", "enhanced", "transformed", "exceeded", "delivered",
        # Innovation & Creation
        "developed", "created", "designed", "built", "engineered", "architected",
        "established", "launched", "pioneered", "innovated", "invented", "spearheaded",
        # Analysis & Strategy
        "analyzed", "evaluated", "assessed", "identified", "researched", "investigated",
        "diagnosed", "forecasted", "strategized", "planned", "recommended",
        # Collaboration & Communication
        "collaborated", "partnered", "communicated", "presented", "negotiated",
        "influenced", "persuaded", "consulted", "advised", "facilitated",
        # Implementation & Execution
        "implemented", "executed", "deployed", "integrated", "automated", "configured",
        "maintained", "operated", "administered", "monitored", "resolved",
    }
    
    # Soft skills that recruiters look for
    SOFT_SKILLS = {
        "leadership", "communication", "teamwork", "problem-solving", "critical thinking",
        "analytical", "strategic thinking", "creativity", "adaptability", "time management",
        "project management", "stakeholder management", "cross-functional", "collaboration",
        "presentation", "negotiation", "decision-making", "conflict resolution",
    }
    
    # Common certifications that boost ATS scores
    CERTIFICATIONS = {
        "aws certified", "azure certified", "gcp certified", "pmp", "cissp", "cism",
        "comptia", "ccna", "ccnp", "ccie", "cka", "ckad", "certified scrum master",
        "csm", "pmi", "itil", "six sigma", "cfa", "cpa", "mba", "ph.d", "phd",
    }

    def __init__(self):
        """
        Initialize service with API configuration.
        """
        self.api_key = os.environ.get("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", "")
        if not self.api_key:
            raise TailoringPipelineError("OPENAI_API_KEY is not configured.")
        if OpenAI is None:
            raise TailoringPipelineError(
                "openai package is not installed. Run `pip install openai` first."
            )

        self.model = os.environ.get("OPENAI_MODEL") or getattr(
            settings,
            "OPENAI_MODEL",
            "gpt-4o-mini",
        )
        self.client = OpenAI(api_key=self.api_key)

    # --------------------------------------------------------------------- #
    # Public helpers                                                        #
    # --------------------------------------------------------------------- #

    def run_workflow(
        self,
        job_description: str,
        experience_graph: dict,
        *,
        parameters: Optional[Dict[str, object]] = None,
        source_url: str = "",
    ) -> Dict[str, object]:
        """
        Analyze a job description and generate tailored resume content.

        Args:
            job_description: Text from raw description or user input.
            experience_graph: User's experience data as a dictionary.
            parameters: Tailoring preferences supplied by the user.
            source_url: Optional URL that OpenAI will fetch via web search grounding.

        Returns:
            Dict representing tailored resume content and metadata.
        """
        if not job_description and not source_url:
            raise TailoringPipelineError("Job description content is required.")

        normalized_parameters = self.normalize_parameters(parameters or {})
        
        # When using web search, try to fetch job description first
        # Note: Many job sites block automated access, so this may fail
        if source_url and not job_description:
            logger.info(f"Attempting to fetch job description from URL: {source_url}")
            fetched_description = self._fetch_job_description_from_url(source_url)
            
            if fetched_description:
                job_description = fetched_description
                logger.info(f"Successfully fetched {len(job_description)} chars from web search")
            else:
                logger.warning(
                    f"Could not fetch job description from {source_url}. "
                    f"Website may be blocking automated access. "
                    f"Will proceed with URL-only mode (requirements extraction will happen during resume generation)."
                )
                # Don't fail - we'll still pass the URL to OpenAI for grounding during resume generation
        
        cleaned_description = self._clean_text(job_description)
        requirements = self._extract_job_requirements(cleaned_description)
        job_profile = self._build_job_profile(
            job_description=cleaned_description,
            requirements=requirements,
            source_url=source_url,
        )

        selected_snippets = self._collect_experience_snippets(
            experience_graph=experience_graph or {},
            job_profile=job_profile,
            limit_per_bucket=self.MAX_SNIPPETS_PER_BUCKET,
        )

        result = self._generate_resume_package(
            job_profile=job_profile,
            selected_snippets=selected_snippets,
            parameters=normalized_parameters,
        )

        # Use updated requirements from job_profile (may have been enhanced by web search)
        final_requirements = job_profile.requirements

        all_bullets = result.bullets or self._flatten_sections(result.sections)
        optimizer = ResumeOptimizer()
        ats_score = optimizer.calculate_ats_score(
            bullet_points=all_bullets,
            job_keywords=final_requirements.get("keywords", []),
            required_skills=final_requirements.get("required_skills", []),
            preferred_skills=final_requirements.get("preferred_skills", []),
        )

        bullet_validations = []
        for detail in result.bullet_details[:10]:
            bullet_text = detail.get("text") or ""
            validation = optimizer.validate_bullet_point(bullet_text)
            if not validation["valid"] or validation.get("suggestions"):
                bullet_validations.append(
                    {
                        "bullet": bullet_text[:50] + "..." if len(bullet_text) > 50 else bullet_text,
                        "issues": validation.get("issues", []),
                        "suggestions": validation.get("suggestions", []),
                    }
                )

        # Combine AI suggestions with ATS insights intelligently
        enhanced_suggestions = []
        
        # Start with ATS-specific critical findings
        if ats_score["missing_critical"] and len(ats_score["missing_critical"]) > 0:
            # Filter out single-letter or trivial terms
            meaningful_missing = [
                skill for skill in ats_score["missing_critical"][:5] 
                if len(skill) > 2 and skill.lower() not in ['aid', 'the', 'and', 'or']
            ]
            if meaningful_missing:
                if len(meaningful_missing) == 1:
                    enhanced_suggestions.append(
                        f"Add required skill: {meaningful_missing[0]} - Include specific examples from your experience"
                    )
                else:
                    enhanced_suggestions.append(
                        f"Add required skills: {', '.join(meaningful_missing[:3])} - Weave these into your achievement descriptions"
                    )
        
        # Add AI-generated suggestions (these are more contextual)
        if result.suggestions:
            # Filter out generic/unhelpful suggestions
            quality_suggestions = [
                s for s in result.suggestions 
                if len(s) > 20 and not s.lower().startswith(('enhance', 'improve', 'emphasize'))
            ]
            enhanced_suggestions.extend(quality_suggestions[:3])
        
        # Add ATS score context if it needs improvement
        if ats_score["overall_score"] < 70:
            enhanced_suggestions.append(
                f"ATS Score: {ats_score['overall_score']}% - Focus on incorporating missing required skills with concrete examples"
            )
        elif ats_score["overall_score"] >= 85:
            enhanced_suggestions.append(
                f"Strong ATS Score: {ats_score['overall_score']}% - Your resume aligns well with job requirements"
            )
        
        # If we don't have enough quality suggestions, add ATS insights
        if len(enhanced_suggestions) < 3 and ats_score.get("suggestions"):
            for suggestion in ats_score["suggestions"]:
                if len(enhanced_suggestions) >= 5:
                    break
                if suggestion not in enhanced_suggestions:
                    enhanced_suggestions.append(suggestion)

        guardrail_dict = [finding for finding in result.guardrail_report]

        debug_payload = {
            "requirements": final_requirements,
            "job_profile": job_profile.to_prompt_dict(),
            "selected_snippets": {
                bucket: [snippet.to_prompt_dict() for snippet in snippets]
                for bucket, snippets in selected_snippets.items()
            },
            "parameters": normalized_parameters,
            "resume_generation": result.debug.get("resume_generation"),
            "guardrails": guardrail_dict,
            "cover_letter_generation": result.debug.get("cover_letter_generation"),
        }

        return {
            "title": result.title,
            "sections": result.sections,
            "bullets": all_bullets,
            "summary": result.summary,
            "suggestions": enhanced_suggestions,
            "cover_letter": result.cover_letter,
            "cover_letter_talking_points": result.cover_letter_talking_points,
            "bullet_details": result.bullet_details,
            "token_usage": result.token_usage,
            "run_id": result.run_id,
            "ats_score": ats_score,
            "bullet_quality": {
                "total_bullets": len(all_bullets),
                "issues_found": len(bullet_validations),
                "validations": bullet_validations[:5],
                "guardrails": guardrail_dict,
            },
            "guardrail_report": guardrail_dict,
            "section_layout": normalized_parameters.get("section_layout", []),
            "debug": debug_payload,
            "words_generated": result.words_generated,
        }

    def _generate_resume_package(
        self,
        *,
        job_profile: JobProfile,
        selected_snippets: Dict[str, List[ExperienceSnippet]],
        parameters: Dict[str, object],
    ) -> TailoringResult:
        token_usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        debug_refs: Dict[str, Any] = {}

        # Use 'sections' parameter if provided, otherwise fall back to 'section_layout'
        # 'sections' = user's requested sections, 'section_layout' = default ordering
        requested_sections = parameters.get("sections", []) or parameters.get("section_layout", [])
        section_plan = self._plan_sections(selected_snippets, requested_sections)
        experience_payload = self._snippets_prompt_payload(selected_snippets)

        stretch_level = parameters.get("stretch_level", 2)
        stretch_guidance = self.STRETCH_LEVEL_DESCRIPTORS.get(
            stretch_level,
            "Balanced: Blend facts with light amplification (≤10% metric lift).",
        )

        bullets_per_section = parameters.get("bullets_per_section", 3)
        
        generation_payload = {
            "job_profile": job_profile.to_prompt_dict(),
            "experience_snippets": experience_payload,
            "section_plan": section_plan,
            "parameters": {
                "tone": parameters.get("tone"),
                "bullets_per_section": bullets_per_section,
                "include_summary": parameters.get("include_summary", True),
                "stretch_level": stretch_level,
                "stretch_guidance": stretch_guidance,
            },
            "generation_rules": [
                f"CRITICAL: Generate EXACTLY {bullets_per_section} bullet points for EACH section listed in section_plan. DO NOT generate more bullets for one section and fewer for another.",
                f"Each section in your output must contain exactly {bullets_per_section} bullets - no more, no fewer. Distribute bullets evenly across all sections.",
                "Use snippet achievements verbatim where possible; never invent employers or roles.",
                "Start every bullet with a strong action verb (Built, Architected, Developed, Led, Optimized, etc.) and include quantifiable metrics when provided.",
                "Respect the stretch guidance—do not exceed the allowed exaggeration from source achievements.",
                "Maintain ATS-friendly length (100-180 characters) and mirror critical job keywords naturally, while sounding like a human.",
                "Return bullet objects with snippet references and stretch assessment (0-3).",
                "NEVER use '+' as substitutes for 'and' - always spell out 'and' in full (e.g., 'React and TypeScript', not 'React + TypeScript').",
                "Write in complete, professional sentences with proper grammar and punctuation.",
                "Provide context for each achievement: explain WHAT you built, WHY it mattered, and the IMPACT it delivered.",
                "Use industry-standard terminology and avoid casual language or abbreviations without context.",
                "When mentioning technologies, integrate them naturally into the achievement narrative rather than listing them.",
                "Quantify impact with specific metrics: percentages, dollar amounts, time savings, user counts, or performance improvements.",
                "Ensure each bullet demonstrates business value, not just technical tasks completed.",
                "Avoid redundant or vague phrases like 'enhancing user experience' - be specific about the enhancement and its measurable outcome.",
            ],
            "output_schema": {
                "title": "str - Job title the candidate is targeting",
                "summary": "optional str - 2-3 sentence compelling value proposition tailored to this specific role",
                "job_location": {
                    "city": "optional str",
                    "state": "optional str",
                    "country": "optional str",
                    "latitude": "optional float",
                    "longitude": "optional float",
                },
                "job_requirements": {
                    "description": "optional str - When using web search, include extracted job description here",
                    "required_skills": "optional list[str] - Required technical and soft skills",
                    "preferred_skills": "optional list[str] - Preferred/nice-to-have skills",
                    "responsibilities": "optional list[str] - Key responsibilities",
                    "qualifications": "optional list[str] - Required qualifications",
                },
                "sections": [
                    {
                        "name": "str - MUST use exact section name from section_plan (DO NOT change or rename - copy the exact string)",
                        "bullets": f"Array of EXACTLY {bullets_per_section} bullet objects (not fewer, not more). Each bullet must be a separate object:",
                        "bullet_structure": {
                            "id": "str",
                            "snippet_id": "str",
                            "text": "str - Complete sentence with strong action verb, context, and quantifiable impact",
                            "stretch": "int 0-3",
                            "metrics": "optional list[str]",
                        },
                    }
                ],
                "suggestions": [
                    "str - Specific, actionable recommendations (e.g., 'Add experience with containerization using Docker or Kubernetes to align with DevOps requirements', NOT generic advice like 'Emphasize technical skills')"
                ],
            },
        }

        grounding = None
        if job_profile.source_url:
            grounding = {
                "type": "web_search",
                "web_search": {
                    "queries": [f"job posting {job_profile.source_url}"]
                },
            }
            # Include URL in the payload so the model knows to search for it
            generation_payload["job_posting_url"] = job_profile.source_url

        # Build instructions - make JSON requirement explicit when using web search
        base_instructions = (
            "You are an elite resume strategist specializing in ATS-optimized, results-driven professional documents. "
            "Your goal is to craft compelling bullet points that pass ATS screening while showcasing quantifiable impact.\n\n"
            
            "SECTION STRUCTURE (CRITICAL - FOLLOW EXACTLY):\n"
            "- The 'section_plan' field contains an array of sections with 'name' and 'snippet_ids'\n"
            "- For each section in section_plan, create a section in your output with the EXACT SAME NAME\n"
            "- COPY THE SECTION NAME CHARACTER-FOR-CHARACTER from section_plan.name to your output sections[].name\n"
            "- DO NOT rename, paraphrase, or modify section names in any way\n"
            "- DO NOT reorder sections - use the same order as section_plan\n"
            "- Example: If section_plan has 'Team Leadership', your output MUST have 'Team Leadership' (not 'Leadership' or 'Team Management')\n"
            "- Example: If section_plan has 'Software Skills', your output MUST have 'Software Skills' (not 'Technical Skills' or 'Skills')\n"
            "- Use ONLY the snippet_ids listed for each section in the section_plan\n\n"
            
            "CRITICAL WRITING STANDARDS:\n"
            "- NEVER use '+' as abbreviations for 'and' (write 'React and TypeScript', not 'React + TypeScript')\n"
            "- Use complete, professional sentences with proper grammar\n"
            "- Integrate technologies naturally within achievement narratives, not as standalone lists\n"
            "- Start each bullet with strong action verbs: Architected, Engineered, Optimized, Spearheaded, etc.\n\n"
            
            "BULLET POINT QUALITY REQUIREMENTS:\n"
            "- Provide full context: WHAT was built, WHY it mattered (business need), and IMPACT delivered\n"
            "- Include specific, quantifiable metrics: percentages, dollar amounts, time savings, scale (users/requests/data volume)\n"
            "- Demonstrate business value and outcomes, not just technical tasks\n"
            "- Avoid vague phrases like 'enhancing user experience' - quantify the enhancement\n"
            "- Each bullet should tell a mini-story of problem → solution → measurable result\n\n"
            
            "ATS OPTIMIZATION:\n"
            "- Mirror job posting keywords naturally within achievement descriptions\n"
            "- Maintain 100-180 character length for optimal ATS parsing\n"
            "- Use industry-standard terminology that matches the job description\n"
            "- Ensure required skills appear in context, not as disconnected terms\n\n"
            
            "PROFESSIONAL SUMMARY GUIDELINES:\n"
            "- Write a compelling 2-3 sentence value proposition tailored to this specific role\n"
            "- Lead with years of experience and core expertise areas\n"
            "- Highlight 2-3 key achievements or specializations that align with job requirements\n"
            "- Avoid generic statements - make it specific to the candidate's background and this opportunity\n\n"
            
            "AI SUGGESTIONS REQUIREMENTS:\n"
            "- Provide 3-5 specific, actionable recommendations (not generic platitudes)\n"
            "- Focus on gaps between candidate experience and job requirements\n"
            "- Suggest concrete ways to strengthen keyword coverage with real examples\n"
            "- Identify missing technical skills or certifications that would improve candidacy\n"
            "- Recommend quantifiable metrics that could be added if the candidate provides them\n\n"
        )
        
        if grounding:
            # When using web search, be extremely explicit about JSON format requirement
            instructions = (
                base_instructions +
                "OUTPUT FORMAT (CRITICAL - READ CAREFULLY):\n"
                "- If job_posting_url is provided, use web search to get complete job posting details\n"
                "- Extract job location with approximate latitude/longitude if possible\n"
                "- CRITICALLY IMPORTANT: Extract and include the job requirements in the job_requirements field:\n"
                "  * description: Full job description text\n"
                "  * required_skills: List of must-have technical and soft skills\n"
                "  * preferred_skills: List of nice-to-have skills\n"
                "  * responsibilities: Key duties and responsibilities\n"
                "  * qualifications: Required qualifications (education, experience, etc.)\n"
                "- YOU MUST RETURN ONLY A SINGLE VALID JSON OBJECT - NO NARRATIVE TEXT, NO MARKDOWN, NO EXPLANATIONS\n"
                "- DO NOT write any introductory text like 'Based on...', 'Here is...', etc.\n"
                "- DO NOT wrap the JSON in markdown code blocks (no ```json or ``` markers)\n"
                "- DO NOT include any text before or after the JSON object\n"
                "- START YOUR RESPONSE WITH THE OPENING { CHARACTER\n"
                "- END YOUR RESPONSE WITH THE CLOSING } CHARACTER\n"
                "- The JSON must exactly match the provided output_schema structure\n"
                "- All text fields must be professional, polished, and ready for direct use in a resume"
            )
        else:
            instructions = (
                base_instructions +
                "OUTPUT FORMAT:\n"
                "- Extract job location with approximate latitude/longitude if possible\n"
                "- Return pure JSON matching the schema (no markdown, no code blocks, no extra text)\n"
                "- Ensure all text fields are professional, polished, and ready for direct use in a resume"
            )

        resume_payload, run_id, resume_usage = self._call_openai_json(
            instructions=instructions,
            payload=generation_payload,
            temperature=float(parameters.get("temperature", 0.35)),
            max_output_tokens=int(parameters.get("max_output_tokens", 3500)),
            grounding=grounding,
        )

        debug_refs["resume_generation"] = resume_payload
        self._merge_usage(token_usage_totals, resume_usage)

        # Extract job requirements if provided by the model (when using web search)
        job_requirements = resume_payload.get("job_requirements", {})
        if job_requirements and isinstance(job_requirements, dict):
            # Update job_profile with extracted requirements
            if job_requirements.get("description"):
                extracted_desc = str(job_requirements["description"])
                if len(extracted_desc) > len(job_profile.description):
                    logger.info(f"Updating job profile with {len(extracted_desc)} chars from AI web search")
                    job_profile.description = extracted_desc
                    
                    # Re-extract requirements from the AI-provided description
                    updated_requirements = self._extract_job_requirements(extracted_desc)
                    job_profile.requirements = updated_requirements
                    job_profile.requirement_buckets = self._bucketize_requirements(updated_requirements)
                    logger.info(
                        f"Extracted from AI response: {len(updated_requirements.get('keywords', []))} keywords, "
                        f"{len(updated_requirements.get('required_skills', []))} required skills"
                    )
            
            # Also extract direct skill lists if provided
            if job_requirements.get("required_skills"):
                existing_required = set(job_profile.requirements.get("required_skills", []))
                ai_required = [str(s) for s in job_requirements["required_skills"]]
                job_profile.requirements["required_skills"] = sorted(existing_required | set(ai_required))
            
            if job_requirements.get("preferred_skills"):
                existing_preferred = set(job_profile.requirements.get("preferred_skills", []))
                ai_preferred = [str(s) for s in job_requirements["preferred_skills"]]
                job_profile.requirements["preferred_skills"] = sorted(existing_preferred | set(ai_preferred))

        # Extract location data if provided by the model
        job_location = resume_payload.get("job_location", {})
        if job_location and isinstance(job_location, dict):
            lat = job_location.get("latitude")
            lon = job_location.get("longitude")
            if lat is not None and lon is not None:
                job_profile.location_coordinates = {"lat": float(lat), "lon": float(lon)}
            city_parts = []
            if job_location.get("city"):
                city_parts.append(str(job_location["city"]))
            if job_location.get("state"):
                city_parts.append(str(job_location["state"]))
            if job_location.get("country"):
                city_parts.append(str(job_location["country"]))
            if city_parts:
                job_profile.location_name = ", ".join(city_parts)

        sections, flat_bullets, bullet_details = self._parse_resume_sections(
            resume_payload,
            default_stretch=stretch_level,
        )
        
        # STEP 2: Validate and fix section/bullet distribution
        # Check if all requested sections are present with correct bullet counts
        sections, flat_bullets, bullet_details = self._validate_and_fix_sections(
            sections=sections,
            flat_bullets=flat_bullets,
            bullet_details=bullet_details,
            requested_sections=requested_sections,
            bullets_per_section=bullets_per_section,
            job_profile=job_profile,
            experience_payload=experience_payload,
            parameters=parameters,
            token_usage_totals=token_usage_totals,
            stretch_level=stretch_level,
        )

        result = TailoringResult(
            title=str(resume_payload.get("title", "")),
            sections=sections,
            bullets=flat_bullets,
            bullet_details=bullet_details,
            summary=str(resume_payload.get("summary", ""))
            if parameters.get("include_summary", True)
            else "",
            suggestions=[str(s) for s in (resume_payload.get("suggestions") or [])],
            cover_letter="",
            cover_letter_talking_points=[],
            token_usage=dict(token_usage_totals),
            run_id=run_id,
            guardrail_report=[],
            debug={"resume_generation": resume_payload},
            job_location_name=job_profile.location_name,
            job_location_coordinates=job_profile.location_coordinates,
        )

        snippet_map = self._snippets_by_id(selected_snippets)
        guard_report, guard_usage, guard_debug, replacements = self._apply_guardrails(
            job_profile=job_profile,
            parameters=parameters,
            bullet_details=result.bullet_details,
            snippet_map=snippet_map,
        )

        if guard_debug:
            debug_refs["guardrails"] = guard_debug
        if guard_report:
            result.guardrail_report = guard_report
        if guard_usage:
            self._merge_usage(token_usage_totals, guard_usage)
            result.token_usage = dict(token_usage_totals)

        if replacements:
            bullet_lookup = {detail["id"]: detail for detail in result.bullet_details}
            for bullet_id, replacement in replacements.items():
                if bullet_id in bullet_lookup:
                    bullet_lookup[bullet_id].update({
                        "text": replacement.get("text", bullet_lookup[bullet_id]["text"]),
                        "stretch": replacement.get("stretch", bullet_lookup[bullet_id].get("stretch")),
                        "metrics": replacement.get("metrics", bullet_lookup[bullet_id].get("metrics")),
                    })

            updated_details = list(bullet_lookup.values())
            result.bullet_details = updated_details
            sections, flat_bullets = self._compose_sections_from_details(updated_details)
            result.sections = sections
            result.bullets = flat_bullets

        if parameters.get("include_cover_letter", False):
            cover_letter, talking_points, cover_usage, cover_debug = self._generate_cover_letter(
                job_profile=job_profile,
                selected_snippets=selected_snippets,
                parameters=parameters,
            )
            result.cover_letter = cover_letter
            result.cover_letter_talking_points = talking_points
            if cover_usage:
                self._merge_usage(token_usage_totals, cover_usage)
                result.token_usage = dict(token_usage_totals)
            if cover_debug:
                debug_refs["cover_letter_generation"] = cover_debug

        result.token_usage = dict(token_usage_totals)
        result.debug.update(debug_refs)

        return result

    def _validate_and_fix_sections(
        self,
        *,
        sections: List[Dict[str, List[str]]],
        flat_bullets: List[str],
        bullet_details: List[Dict[str, object]],
        requested_sections: List[str],
        bullets_per_section: int,
        job_profile: JobProfile,
        experience_payload: Dict[str, List[Dict[str, object]]],
        parameters: Dict[str, object],
        token_usage_totals: Dict[str, int],
        stretch_level: int,
    ) -> Tuple[List[Dict[str, List[str]]], List[str], List[Dict[str, object]]]:
        """
        Validate that all requested sections are present with the correct number of bullets.
        Regenerate missing or incomplete sections individually.
        
        Returns updated (sections, flat_bullets, bullet_details) tuple.
        """
        # Build lookup of existing sections
        existing_sections = {s.get("name", ""): s for s in sections}
        existing_section_names = set(existing_sections.keys())
        
        # Identify missing or incomplete sections
        sections_to_fix = []
        for section_name in requested_sections:
            if section_name not in existing_section_names:
                sections_to_fix.append({
                    "name": section_name,
                    "reason": "missing",
                    "current_count": 0,
                    "needed": bullets_per_section,
                })
            else:
                current_count = len(existing_sections[section_name].get("bullets", []))
                if current_count < bullets_per_section:
                    sections_to_fix.append({
                        "name": section_name,
                        "reason": "incomplete",
                        "current_count": current_count,
                        "needed": bullets_per_section - current_count,
                    })
        
        if not sections_to_fix:
            logger.info(f"All {len(requested_sections)} sections validated with {bullets_per_section} bullets each")
            return sections, flat_bullets, bullet_details
        
        logger.info(f"Fixing {len(sections_to_fix)} sections: {[s['name'] for s in sections_to_fix]}")
        
        # Regenerate each problematic section individually
        for fix_info in sections_to_fix:
            section_name = fix_info["name"]
            needed_bullets = fix_info["needed"] if fix_info["reason"] == "incomplete" else bullets_per_section
            
            logger.info(f"Regenerating section '{section_name}': need {needed_bullets} bullets")
            
            new_bullets, new_details, section_usage = self._generate_single_section(
                section_name=section_name,
                bullet_count=needed_bullets,
                job_profile=job_profile,
                experience_payload=experience_payload,
                parameters=parameters,
                stretch_level=stretch_level,
            )
            
            self._merge_usage(token_usage_totals, section_usage)
            
            if new_bullets:
                if fix_info["reason"] == "missing":
                    # Add new section
                    sections.append({"name": section_name, "bullets": new_bullets})
                else:
                    # Append to existing section
                    existing_sections[section_name]["bullets"].extend(new_bullets)
                
                flat_bullets.extend(new_bullets)
                
                # Assign proper indices to new bullet details
                section_index = next(
                    (i for i, s in enumerate(sections) if s.get("name") == section_name),
                    len(sections) - 1
                )
                for detail in new_details:
                    detail["section"] = section_name
                    detail["section_index"] = section_index
                    bullet_details.append(detail)
                
                logger.info(f"Added {len(new_bullets)} bullets to section '{section_name}'")
            else:
                logger.warning(f"Failed to generate bullets for section '{section_name}'")
        
        # Reorder sections to match requested order
        ordered_sections = []
        for section_name in requested_sections:
            for section in sections:
                if section.get("name") == section_name:
                    ordered_sections.append(section)
                    break
        
        # Add any sections not in the requested list at the end
        for section in sections:
            if section not in ordered_sections:
                ordered_sections.append(section)
        
        return ordered_sections, flat_bullets, bullet_details

    def _generate_single_section(
        self,
        *,
        section_name: str,
        bullet_count: int,
        job_profile: JobProfile,
        experience_payload: Dict[str, List[Dict[str, object]]],
        parameters: Dict[str, object],
        stretch_level: int,
    ) -> Tuple[List[str], List[Dict[str, object]], Dict[str, int]]:
        """
        Generate bullets for a single section using a focused prompt.
        Uses lower max_output_tokens for faster response.
        
        Returns (bullets_list, bullet_details, token_usage)
        """
        stretch_guidance = self.STRETCH_LEVEL_DESCRIPTORS.get(
            stretch_level,
            "Balanced: Blend facts with light amplification (≤10% metric lift).",
        )
        
        generation_payload = {
            "section_name": section_name,
            "bullet_count": bullet_count,
            "job_profile": job_profile.to_prompt_dict(),
            "experience_snippets": experience_payload,
            "parameters": {
                "tone": parameters.get("tone"),
                "stretch_level": stretch_level,
                "stretch_guidance": stretch_guidance,
            },
        }
        
        instructions = (
            f"Generate EXACTLY {bullet_count} resume bullet points for the section '{section_name}'.\n\n"
            "CRITICAL REQUIREMENTS:\n"
            f"- Output EXACTLY {bullet_count} bullets - no more, no fewer\n"
            "- Each bullet must start with a strong action verb\n"
            "- Include quantifiable metrics where possible\n"
            "- Match the job requirements and keywords naturally\n"
            "- Use achievements from the experience_snippets provided\n"
            "- Keep bullets between 100-180 characters for ATS optimization\n\n"
            "OUTPUT FORMAT (JSON only, no markdown):\n"
            "{\n"
            '  "bullets": [\n'
            '    {"id": "fix-1", "text": "bullet text here", "stretch": 2},\n'
            '    ... (repeat for each bullet)\n'
            "  ]\n"
            "}"
        )
        
        try:
            response, _run_id, usage = self._call_openai_json(
                instructions=instructions,
                payload=generation_payload,
                temperature=float(parameters.get("temperature", 0.35)),
                max_output_tokens=800,  # Lower limit for faster single-section generation
            )
            
            raw_bullets = response.get("bullets", [])
            bullets: List[str] = []
            details: List[Dict[str, object]] = []
            
            for idx, bullet_entry in enumerate(raw_bullets):
                if isinstance(bullet_entry, dict):
                    text = str(bullet_entry.get("text", "")).strip()
                    bullet_id = str(bullet_entry.get("id", f"fix-{idx+1}"))
                    stretch_val = int(bullet_entry.get("stretch", stretch_level))
                else:
                    text = str(bullet_entry).strip()
                    bullet_id = f"fix-{idx+1}"
                    stretch_val = stretch_level
                
                if text:
                    bullets.append(text)
                    details.append({
                        "id": bullet_id,
                        "text": text,
                        "stretch": stretch_val,
                        "snippet_id": "",
                        "bullet_index": idx,
                    })
            
            return bullets, details, usage
            
        except Exception as e:
            logger.error(f"Failed to generate section '{section_name}': {e}")
            return [], [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _apply_guardrails(
        self,
        *,
        job_profile: JobProfile,
        parameters: Dict[str, object],
        bullet_details: List[Dict[str, object]],
        snippet_map: Dict[str, ExperienceSnippet],
    ) -> Tuple[List[Dict[str, object]], Dict[str, int], Optional[Dict[str, Any]], Dict[str, Dict[str, object]]]:
        if not bullet_details:
            return [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, None, {}

        stretch_level = parameters.get("stretch_level", 2)
        stretch_guidance = self.STRETCH_LEVEL_DESCRIPTORS.get(
            stretch_level,
            "Balanced: Blend facts with light amplification (≤10% metric lift).",
        )

        snippet_payload = {
            snippet_id: {
                "summary": snippet.summary,
                "achievements": snippet.achievements,
                "skills": snippet.skills,
                "time_frame": snippet.time_frame,
            }
            for snippet_id, snippet in snippet_map.items()
        }

        candidate_payload = []
        for detail in bullet_details:
            candidate_payload.append(
                {
                    "bullet_id": detail.get("id"),
                    "snippet_id": detail.get("snippet_id"),
                    "text": detail.get("text"),
                    "stretch": detail.get("stretch"),
                    "section": detail.get("section"),
                }
            )

        guard_payload = {
            "stretch_policy": {
                "level": stretch_level,
                "guidance": stretch_guidance,
            },
            "job_keywords": job_profile.requirements.get("keywords", []),
            "required_skills": job_profile.requirements.get("required_skills", []),
            "bullet_candidates": candidate_payload,
            "snippets": snippet_payload,
        }

        guard_response, _guard_run_id, guard_usage = self._call_openai_json(
            instructions=(
                "You audit resume bullets against their source snippets. For each candidate, return a status of"
                " 'ok', 'needs_revision', or 'reject'. Flag 'reject' if claims exceed snippet facts or stretch policy."
            ),
            payload=guard_payload,
            temperature=0.0,
            max_output_tokens=1200,  # Increased for larger bullet lists with detailed analysis
        )

        findings_raw = guard_response.get("findings") or []
        guard_report: List[Dict[str, object]] = []
        flagged: List[Dict[str, object]] = []
        for finding in findings_raw:
            snippet_id = str(finding.get("snippet_id", ""))
            bullet_id = str(finding.get("bullet_id", ""))
            status = str(finding.get("status", "ok")).lower() or "ok"
            reasons = [str(reason) for reason in (finding.get("reasons") or [])]
            guard_item = GuardrailFinding(
                snippet_id=snippet_id,
                bullet_id=bullet_id,
                status=status,
                reasons=reasons,
            ).to_dict()
            guard_report.append(guard_item)
            if status in {"reject", "needs_revision"}:
                flagged.append({
                    "bullet_id": bullet_id,
                    "snippet_id": snippet_id,
                    "status": status,
                    "reasons": reasons,
                    "original_text": next(
                        (detail.get("text") for detail in bullet_details if detail.get("id") == bullet_id),
                        "",
                    ),
                })

        replacements: Dict[str, Dict[str, object]] = {}
        regen_debug: Optional[Dict[str, Any]] = None
        regen_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        if flagged:
            replacements, regen_usage, regen_debug = self._regenerate_bullets(
                flagged=flagged,
                snippet_map=snippet_map,
                job_profile=job_profile,
                parameters=parameters,
            )

        combined_usage = {
            key: guard_usage.get(key, 0) + regen_usage.get(key, 0)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }

        guard_debug = {"analysis": guard_response}
        if regen_debug:
            guard_debug["regeneration"] = regen_debug

        return guard_report, combined_usage, guard_debug, replacements

    def _regenerate_bullets(
        self,
        *,
        flagged: List[Dict[str, object]],
        snippet_map: Dict[str, ExperienceSnippet],
        job_profile: JobProfile,
        parameters: Dict[str, object],
    ) -> Tuple[Dict[str, Dict[str, object]], Dict[str, int], Optional[Dict[str, Any]]]:
        if not flagged:
            return {}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, None

        stretch_level = parameters.get("stretch_level", 2)
        stretch_guidance = self.STRETCH_LEVEL_DESCRIPTORS.get(
            stretch_level,
            "Balanced: Blend facts with light amplification (≤10% metric lift).",
        )

        regeneration_payload = {
            "stretch_policy": {
                "level": stretch_level,
                "guidance": stretch_guidance,
            },
            "job_keywords": job_profile.requirements.get("keywords", []),
            "requests": [],
        }

        for item in flagged:
            snippet = snippet_map.get(item.get("snippet_id"))
            if not snippet:
                continue
            regeneration_payload["requests"].append(
                {
                    "bullet_id": item.get("bullet_id"),
                    "snippet_id": snippet.snippet_id,
                    "original_text": item.get("original_text", ""),
                    "reasons": item.get("reasons", []),
                    "snippet": {
                        "summary": snippet.summary,
                        "achievements": snippet.achievements,
                        "skills": snippet.skills,
                        "time_frame": snippet.time_frame,
                    },
                }
            )

        if not regeneration_payload["requests"]:
            return {}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, None

        regen_response, _regen_run_id, regen_usage = self._call_openai_json(
            instructions=(
                "Rewrite only the flagged bullets using the provided snippet data. Keep within the stretch policy"
                " and output JSON with replacements for each bullet_id."
            ),
            payload=regeneration_payload,
            temperature=0.2,
            max_output_tokens=400,
        )

        replacements_raw = regen_response.get("replacements") or []
        replacements: Dict[str, Dict[str, object]] = {}
        for item in replacements_raw:
            bullet_id = str(item.get("bullet_id"))
            if not bullet_id:
                continue
            replacements[bullet_id] = {
                "text": str(item.get("text", "")).strip(),
                "stretch": int(item.get("stretch", stretch_level)),
                "metrics": item.get("metrics"),
            }

        return replacements, regen_usage, regen_response

    def _generate_cover_letter(
        self,
        *,
        job_profile: JobProfile,
        selected_snippets: Dict[str, List[ExperienceSnippet]],
        parameters: Dict[str, object],
    ) -> Tuple[str, List[str], Dict[str, int], Optional[Dict[str, Any]]]:
        snippet_payload = self._snippets_prompt_payload(selected_snippets)
        inserts = parameters.get("cover_letter_inserts", []) or []

        cover_payload = {
            "job_profile": job_profile.to_prompt_dict(),
            "experience_snippets": snippet_payload,
            "tone": parameters.get("tone", "confident and metric-driven"),
            "stretch_level": parameters.get("stretch_level", 2),
            "user_inserts": inserts,
            "structure": [
                "Paragraph 1: hook that mirrors job mission and highlights relevant experience.",
                "Paragraph 2: connect top 2-3 snippets to job requirements with metrics.",
                "Paragraph 3: close with enthusiasm, availability, and call-to-action.",
            ],
            "output_schema": {
                "cover_letter": "3 paragraphs separated by blank lines",
                "talking_points": "list[str] of 3-5 key highlights",
            },
        }

        cover_response, _cover_run_id, cover_usage = self._call_openai_json(
            instructions=(
                "Compose a tailored cover letter using the provided snippets and inserts. Return JSON with"
                " 'cover_letter' (string) and 'talking_points' (list of strings)."
            ),
            payload=cover_payload,
            temperature=max(0.2, float(parameters.get("temperature", 0.35))),
            max_output_tokens=600,
        )

        cover_letter = str(cover_response.get("cover_letter", "")).strip()
        talking_points = [str(point) for point in (cover_response.get("talking_points") or [])]

        return cover_letter, talking_points, cover_usage, cover_response


    @classmethod
    def normalize_parameters(cls, parameters: Dict[str, object]) -> Dict[str, object]:
        """
        Merge user-specified parameters with defaults and sanitize values.
        """
        merged = {**cls.DEFAULT_PARAMETERS, **parameters}

        sections = merged.get("sections")
        if isinstance(sections, str):
            raw_sections = re.split(r"[\n,]+", sections)
            sections = [section.strip() for section in raw_sections if section.strip()]
        elif isinstance(sections, Iterable):
            sections = [str(section).strip() for section in sections if str(section).strip()]
        else:
            sections = list(cls.DEFAULT_PARAMETERS["sections"])

        merged["sections"] = sections or list(cls.DEFAULT_PARAMETERS["sections"])

        try:
            merged["bullets_per_section"] = max(1, int(merged.get("bullets_per_section", 3)))
        except (TypeError, ValueError):
            merged["bullets_per_section"] = cls.DEFAULT_PARAMETERS["bullets_per_section"]

        try:
            merged["temperature"] = float(merged.get("temperature", cls.DEFAULT_PARAMETERS["temperature"]))
        except (TypeError, ValueError):
            merged["temperature"] = cls.DEFAULT_PARAMETERS["temperature"]

        try:
            merged["max_output_tokens"] = int(
                merged.get("max_output_tokens", cls.DEFAULT_PARAMETERS["max_output_tokens"])
            )
        except (TypeError, ValueError):
            merged["max_output_tokens"] = cls.DEFAULT_PARAMETERS["max_output_tokens"]

        merged["tone"] = (
            str(merged.get("tone", cls.DEFAULT_PARAMETERS["tone"])).strip()
            or cls.DEFAULT_PARAMETERS["tone"]
        )
        merged["include_summary"] = bool(merged.get("include_summary", True))
        merged["include_cover_letter"] = bool(merged.get("include_cover_letter", False))

        try:
            stretch_raw = int(merged.get("stretch_level", cls.DEFAULT_PARAMETERS["stretch_level"]))
        except (TypeError, ValueError):
            stretch_raw = cls.DEFAULT_PARAMETERS["stretch_level"]
        merged["stretch_level"] = max(0, min(3, stretch_raw))

        layout = merged.get("section_layout")
        if isinstance(layout, str):
            raw_layout = re.split(r"[\n,]+", layout)
            layout = [item.strip() for item in raw_layout if item.strip()]
        elif isinstance(layout, Iterable):
            layout = [str(item).strip() for item in layout if str(item).strip()]
        else:
            layout = list(cls.DEFAULT_PARAMETERS["section_layout"])
        merged["section_layout"] = layout or list(cls.DEFAULT_PARAMETERS["section_layout"])
        
        # If user provided 'sections', use those as the section_layout as well
        # 'sections' takes precedence over 'section_layout'
        if "sections" in parameters and merged.get("sections"):
            merged["section_layout"] = merged["sections"]

        inserts = merged.get("cover_letter_inserts") or []
        if isinstance(inserts, str):
            inserts = [item.strip() for item in re.split(r"[\n,]+", inserts) if item.strip()]
        elif isinstance(inserts, Iterable):
            inserts = [str(item).strip() for item in inserts if str(item).strip()]
        else:
            inserts = []
        merged["cover_letter_inserts"] = inserts
        
        # Enforce token limits to prevent JSON truncation and excessive costs
        # Hard limits from UI configuration
        ABSOLUTE_MIN_TOKENS = 1000
        ABSOLUTE_MAX_TOKENS = 6500
        
        # Calculate required tokens based on configuration
        min_tokens = 2500  # Base minimum for resume generation
        
        # Cover letter needs separate API call, doesn't affect resume token limit
        # But having many bullets or sections increases resume token needs
        if merged.get("bullets_per_section", 3) >= 5:
            min_tokens = max(min_tokens, 3000)  # Many bullets need more tokens
        
        num_sections = len(merged.get("sections", [])) or len(merged.get("section_layout", []))
        if num_sections >= 3 and merged.get("bullets_per_section", 3) >= 4:
            min_tokens = max(min_tokens, 3500)  # 3+ sections with 4+ bullets each
        
        # Apply absolute minimum (UI constraint)
        min_tokens = max(min_tokens, ABSOLUTE_MIN_TOKENS)
        
        # If user's max_output_tokens is too low, increase it and log warning
        if merged["max_output_tokens"] < min_tokens:
            logger.warning(
                f"max_output_tokens ({merged['max_output_tokens']}) is below safe minimum ({min_tokens}) "
                f"for current configuration (sections={num_sections}, "
                f"bullets_per_section={merged.get('bullets_per_section')}). "
                f"Automatically increasing to {min_tokens} to prevent JSON truncation."
            )
            merged["max_output_tokens"] = min_tokens
        
        # Apply absolute maximum (UI constraint and cost control)
        if merged["max_output_tokens"] > ABSOLUTE_MAX_TOKENS:
            logger.warning(
                f"max_output_tokens ({merged['max_output_tokens']}) exceeds maximum allowed ({ABSOLUTE_MAX_TOKENS}). "
                f"Capping at {ABSOLUTE_MAX_TOKENS} for cost control."
            )
            merged["max_output_tokens"] = ABSOLUTE_MAX_TOKENS

        return merged

    # --------------------------------------------------------------------- #
    # Internal helpers                                                      #
    # --------------------------------------------------------------------- #

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"\s+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _extract_keywords(self, text: str) -> List[str]:
        """
        Extract ATS-relevant keywords including tech terms, action verbs, and soft skills.
        """
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9\+#\./-]{1,}", text)
        keywords: List[str] = []
        text_lower = text.lower()
        
        # Check for multi-word certifications first
        for cert in self.CERTIFICATIONS:
            if cert in text_lower:
                keywords.append(cert)
        
        # Extract single tokens
        for token in tokens:
            token_clean = token.strip(" .,;:()[]{}").lower()
            if len(token_clean) < 2 or token_clean in STOPWORDS:
                continue
            
            # Include if it's a tech keyword, action verb, soft skill, or proper noun
            if (token_clean in self.TECH_KEYWORDS or 
                token_clean in self.ATS_ACTION_VERBS or
                token_clean in self.SOFT_SKILLS or
                token.istitle() or token.isupper()):
                keywords.append(token_clean)
        
        return keywords

    def _extract_job_requirements(self, job_description: str) -> Dict[str, List[str]]:
        """
        Enhanced extraction of requirements with ATS-critical categorization.
        Distinguishes between required/preferred, hard/soft skills, and certifications.
        """
        requirements = {
            "skills": [],
            "qualifications": [],
            "responsibilities": [],
            "keywords": [],
            "required_skills": [],  # Must-have skills
            "preferred_skills": [],  # Nice-to-have skills
            "certifications": [],
            "action_verbs": [],
            "years_experience": [],
            "education": [],
        }

        if not job_description:
            return requirements

        current_bucket = "responsibilities"
        is_required_section = False
        is_preferred_section = False
        skill_candidates: set[str] = set()
        keyword_candidates: List[str] = []
        text_lower = job_description.lower()

        # Extract years of experience requirements
        exp_patterns = [
            r"(\d+)\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|exp)",
            r"minimum\s+(?:of\s+)?(\d+)\s+(?:years?|yrs?)",
            r"at least\s+(\d+)\s+(?:years?|yrs?)",
        ]
        for pattern in exp_patterns:
            matches = re.finditer(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                years = match.group(1)
                requirements["years_experience"].append(f"{years}+ years")

        # Extract education requirements
        education_keywords = ["bachelor", "master", "phd", "ph.d", "mba", "degree", "b.s.", "m.s."]
        for edu_kw in education_keywords:
            if edu_kw in text_lower:
                # Find the line containing this education requirement
                for line in job_description.splitlines():
                    if edu_kw in line.lower():
                        requirements["education"].append(line.strip().lstrip("-*•· "))
                        break

        # Process line by line
        for raw_line in job_description.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            lowered = line.lower()
            
            # Detect section headers
            if "responsibil" in lowered or "duties" in lowered or "you will" in lowered:
                current_bucket = "responsibilities"
                is_required_section = False
                is_preferred_section = False
                continue
            if "qualification" in lowered or "requirements" in lowered or "must have" in lowered:
                current_bucket = "qualifications"
                is_required_section = "required" in lowered or "must" in lowered
                is_preferred_section = "preferred" in lowered or "nice to have" in lowered
                continue
            if "skill" in lowered or "technolog" in lowered or "tools" in lowered or "proficienc" in lowered:
                current_bucket = "skills"
                is_required_section = "required" in lowered or "must" in lowered
                is_preferred_section = "preferred" in lowered or "nice to have" in lowered or "bonus" in lowered
                continue
            if "preferred" in lowered or "nice to have" in lowered or "bonus" in lowered or "plus" in lowered:
                is_preferred_section = True
                is_required_section = False
                continue

            bullet = line.lstrip("-*•· ")
            extracted_keywords = self._extract_keywords(bullet)

            # Check if this line indicates required vs preferred
            line_is_required = any(word in lowered for word in ["required", "must", "essential"])
            line_is_preferred = any(word in lowered for word in ["preferred", "nice to have", "bonus", "plus"])

            if current_bucket == "skills":
                skill_candidates.update(extracted_keywords)
                
                # Categorize as required or preferred
                if line_is_required or (is_required_section and not is_preferred_section):
                    requirements["required_skills"].extend(extracted_keywords)
                elif line_is_preferred or is_preferred_section:
                    requirements["preferred_skills"].extend(extracted_keywords)
                    
            elif current_bucket == "qualifications":
                requirements["qualifications"].append(bullet)
                keyword_candidates.extend(extracted_keywords)
                
                # Check for required qualifications
                if line_is_required or is_required_section:
                    requirements["required_skills"].extend(extracted_keywords)
                elif line_is_preferred or is_preferred_section:
                    requirements["preferred_skills"].extend(extracted_keywords)
            else:
                requirements["responsibilities"].append(bullet)
                keyword_candidates.extend(extracted_keywords)
                
                # Extract action verbs from responsibilities
                for verb in self.ATS_ACTION_VERBS:
                    if verb in lowered:
                        requirements["action_verbs"].append(verb)

        # Extract certifications from all keywords
        all_text_lower = job_description.lower()
        for cert in self.CERTIFICATIONS:
            if cert in all_text_lower:
                requirements["certifications"].append(cert)

        # Deduplicate and sort
        requirements["skills"] = sorted(skill_candidates)
        requirements["keywords"] = sorted(set(keyword_candidates) | set(requirements["skills"]))
        requirements["required_skills"] = sorted(set(requirements["required_skills"]))
        requirements["preferred_skills"] = sorted(set(requirements["preferred_skills"]))
        requirements["certifications"] = sorted(set(requirements["certifications"]))
        requirements["action_verbs"] = sorted(set(requirements["action_verbs"]))
        requirements["years_experience"] = sorted(set(requirements["years_experience"]))
        requirements["education"] = list(set(requirements["education"]))
        
        return requirements

    def _build_job_profile(
        self,
        *,
        job_description: str,
        requirements: Dict[str, List[str]],
        source_url: str,
    ) -> JobProfile:
        buckets = self._bucketize_requirements(requirements)
        truncated_description = job_description[:2000]
        return JobProfile(
            source_url=source_url,
            description=truncated_description,
            requirements=requirements,
            requirement_buckets=buckets,
        )

    def _bucketize_requirements(self, requirements: Dict[str, List[str]]) -> Dict[str, List[str]]:
        buckets = {
            "Professional Experience": [],
            "Leadership": [],
            "Projects": [],
            "Skills & Tools": [],
        }

        leadership_keywords = {"lead", "managed", "coach", "mentor", "director", "executive", "team"}
        project_keywords = {"project", "launch", "build", "deploy", "prototype", "implementation", "initiative"}

        combined_lines = requirements.get("responsibilities", []) + requirements.get("qualifications", [])
        for line in combined_lines:
            lowered = line.lower()
            if any(word in lowered for word in leadership_keywords):
                buckets["Leadership"].append(line)
            elif any(word in lowered for word in project_keywords):
                buckets["Projects"].append(line)
            else:
                buckets["Professional Experience"].append(line)

        skill_lines = requirements.get("required_skills", []) + requirements.get("preferred_skills", [])
        skill_lines = skill_lines or requirements.get("skills", [])
        if skill_lines:
            buckets["Skills & Tools"].extend(sorted(set(skill_lines)))

        return {key: sorted(set(values)) for key, values in buckets.items() if values}

    def _collect_experience_snippets(
        self,
        *,
        experience_graph: dict,
        job_profile: JobProfile,
        limit_per_bucket: int,
    ) -> Dict[str, List[ExperienceSnippet]]:
        if not experience_graph:
            return {}

        raw_entries: List[dict] = []
        for key in ("experiences", "leadership", "projects", "activities"):
            raw_entries.extend(experience_graph.get(key, []))

        snippet_candidates: Dict[str, List[Tuple[float, ExperienceSnippet]]] = {}
        for entry in raw_entries:
            snippet = self._build_snippet_from_entry(entry)
            if not snippet:
                continue
            score = self._score_snippet(snippet, job_profile)
            snippet_candidates.setdefault(snippet.bucket, []).append((score, snippet))

        selected: Dict[str, List[ExperienceSnippet]] = {}
        for bucket, items in snippet_candidates.items():
            sorted_items = sorted(items, key=lambda pair: pair[0], reverse=True)
            top_items = [snippet for _score, snippet in sorted_items[:limit_per_bucket]]
            if top_items:
                selected[bucket] = top_items

        return selected

    def _build_snippet_from_entry(self, entry: dict) -> Optional[ExperienceSnippet]:
        if not entry:
            return None

        raw_id = entry.get("id") or entry.get("uuid")
        snippet_id = str(raw_id or f"snippet-{abs(hash(str(entry))) % 10_000_000}")
        bucket = self._infer_bucket_from_entry(entry)

        title = entry.get("title") or entry.get("role") or entry.get("name") or "Experience"
        organization = entry.get("company") or entry.get("organization") or ""
        timeframe = self._format_timeframe(entry)
        achievements = [str(item).strip() for item in entry.get("achievements", []) if str(item).strip()]
        achievements = achievements[:6]

        description = entry.get("description", "")
        summary_seed = description or " ".join(achievements[:2])
        summary = self._summarize_text(summary_seed, word_limit=45)

        skills = [str(skill).strip() for skill in entry.get("skills", []) if str(skill).strip()]

        return ExperienceSnippet(
            snippet_id=snippet_id,
            bucket=bucket,
            title=title,
            organization=organization,
            time_frame=timeframe,
            summary=summary,
            achievements=achievements,
            skills=skills,
            source_ref=entry,
        )

    def _infer_bucket_from_entry(self, entry: dict) -> str:
        entry_type = str(entry.get("bucket") or entry.get("type") or "").lower()
        if "lead" in entry_type or entry.get("is_leadership"):
            return "Leadership"
        if "project" in entry_type:
            return "Projects"
        if "skill" in entry_type:
            return "Skills & Tools"

        title = str(entry.get("title") or "").lower()
        if any(keyword in title for keyword in ("president", "chair", "captain", "lead")):
            return "Leadership"
        if any(keyword in title for keyword in ("project", "capstone", "hackathon")):
            return "Projects"

        return "Professional Experience"

    def _format_timeframe(self, entry: dict) -> str:
        start = entry.get("start") or entry.get("start_date") or ""
        end = entry.get("end") or entry.get("end_date") or ("Present" if entry.get("current") else "")
        start = str(start).strip()
        end = str(end).strip()
        if start and end:
            return f"{start} - {end}"
        if start:
            return f"{start} - Present"
        return entry.get("time_frame") or ""

    def _summarize_text(self, text: str, *, word_limit: int) -> str:
        tokens = re.findall(r"\w+", text)
        if len(tokens) <= word_limit:
            return text.strip()
        truncated = " ".join(tokens[:word_limit])
        return f"{truncated}..."

    def _score_snippet(self, snippet: ExperienceSnippet, job_profile: JobProfile) -> float:
        job_keywords = set(keyword.lower() for keyword in job_profile.requirements.get("keywords", []))
        required_skills = set(skill.lower() for skill in job_profile.requirements.get("required_skills", []))
        preferred_skills = set(skill.lower() for skill in job_profile.requirements.get("preferred_skills", []))

        snippet_skills = {skill.lower() for skill in snippet.skills}
        achievement_text = " ".join(snippet.achievements).lower()

        score = 0.0
        score += 6 * len(snippet_skills & required_skills)
        score += 3 * len(snippet_skills & preferred_skills)
        score += 1.5 * len(snippet_skills & job_keywords)

        score += sum(1 for kw in job_keywords if kw and kw in achievement_text)

        if snippet.bucket == "Leadership":
            score += 2
        if snippet.bucket == "Projects":
            score += 1
        if snippet.source_ref.get("current"):
            score += 1.5

        return score

    def _plan_sections(
        self,
        selected_snippets: Dict[str, List[ExperienceSnippet]],
        layout: Sequence[str],
    ) -> List[Dict[str, object]]:
        """
        Create a section plan matching user-requested section names to available snippets.
        
        IMPORTANT: All requested sections are ALWAYS included, even if no snippets match.
        The AI will be asked to generate bullets for these sections using all available experience.
        
        Strategy:
        1. Try exact match with bucket names in selected_snippets
        2. If no exact match, distribute available buckets across requested sections
        3. ALL requested sections are included - none are skipped
        4. Use custom section names in output while referencing correct snippet IDs
        """
        if not layout:
            # No custom layout, use bucket names as-is
            return [
                {"name": bucket, "snippet_ids": [s.snippet_id for s in snippets]}
                for bucket, snippets in selected_snippets.items()
            ]
        
        plan: List[Dict[str, object]] = []
        seen_ids: set[str] = set()
        available_buckets = list(selected_snippets.keys())
        bucket_index = 0
        
        # Collect ALL snippet IDs for sections that don't have a direct match
        all_snippet_ids = []
        for snippets in selected_snippets.values():
            for snippet in snippets:
                all_snippet_ids.append(snippet.snippet_id)

        for section_name in layout:
            # Try exact match first
            snippets = selected_snippets.get(section_name)
            
            # If no exact match and we have unused buckets, use the next available bucket
            if not snippets and bucket_index < len(available_buckets):
                actual_bucket = available_buckets[bucket_index]
                snippets = selected_snippets.get(actual_bucket)
                bucket_index += 1
            
            # ALWAYS include the section - even with no dedicated snippets
            # Use all available snippets as the pool
            if not snippets:
                logger.info(
                    f"Section '{section_name}' has no dedicated snippets. "
                    f"Will use full experience pool ({len(all_snippet_ids)} snippets) for generation."
                )
                # Include all snippet IDs so AI can draw from entire experience
                plan.append({
                    "name": section_name,
                    "snippet_ids": all_snippet_ids,
                    "use_full_pool": True,  # Flag to indicate AI should select from all
                })
                continue
                
            snippet_ids = []
            for snippet in snippets:
                if snippet.snippet_id in seen_ids:
                    continue
                seen_ids.add(snippet.snippet_id)
                snippet_ids.append(snippet.snippet_id)
            
            # Even if snippet_ids is empty after dedup, still include the section
            if snippet_ids:
                plan.append({
                    "name": section_name,
                    "snippet_ids": snippet_ids,
                })
            else:
                # Use full pool for this section too
                plan.append({
                    "name": section_name,
                    "snippet_ids": all_snippet_ids,
                    "use_full_pool": True,
                })

        return plan

    def _snippets_prompt_payload(
        self,
        selected_snippets: Dict[str, List[ExperienceSnippet]],
    ) -> Dict[str, List[Dict[str, object]]]:
        return {
            bucket: [snippet.to_prompt_dict() for snippet in snippets]
            for bucket, snippets in selected_snippets.items()
        }

    def _snippets_by_id(
        self,
        selected_snippets: Dict[str, List[ExperienceSnippet]],
    ) -> Dict[str, ExperienceSnippet]:
        mapping: Dict[str, ExperienceSnippet] = {}
        for snippets in selected_snippets.values():
            for snippet in snippets:
                mapping[snippet.snippet_id] = snippet
        return mapping

    def _parse_resume_sections(
        self,
        payload: Dict[str, Any],
        *,
        default_stretch: int,
    ) -> Tuple[List[Dict[str, List[str]]], List[str], List[Dict[str, object]]]:
        raw_sections = payload.get("sections") or []
        if not isinstance(raw_sections, list):
            raw_sections = []

        structured_sections: List[Dict[str, List[str]]] = []
        flat_bullets: List[str] = []
        bullet_details: List[Dict[str, object]] = []

        for section_index, raw_section in enumerate(raw_sections):
            if not isinstance(raw_section, dict):
                continue
            section_name = str(raw_section.get("name", "Highlights"))
            raw_bullets = raw_section.get("bullets") or []
            section_texts: List[str] = []

            for bullet_index, bullet_entry in enumerate(raw_bullets):
                if isinstance(bullet_entry, dict):
                    text = str(bullet_entry.get("text", "")).strip()
                    snippet_id = str(bullet_entry.get("snippet_id", ""))
                    stretch_value = int(bullet_entry.get("stretch", default_stretch))
                    bullet_id = str(bullet_entry.get("id") or f"b{section_index+1}-{bullet_index+1}")
                    metrics = bullet_entry.get("metrics")
                else:
                    text = str(bullet_entry).strip()
                    snippet_id = ""
                    stretch_value = default_stretch
                    bullet_id = f"b{section_index+1}-{bullet_index+1}"
                    metrics = None

                if not text:
                    continue

                section_texts.append(text)
                flat_bullets.append(text)

                detail = {
                    "id": bullet_id,
                    "snippet_id": snippet_id,
                    "text": text,
                    "stretch": stretch_value,
                    "section": section_name,
                    "section_index": section_index,
                    "bullet_index": bullet_index,
                }
                if metrics:
                    detail["metrics"] = metrics

                bullet_details.append(detail)

            structured_sections.append({"name": section_name, "bullets": section_texts})

        return structured_sections, flat_bullets, bullet_details

    def _compose_sections_from_details(
        self,
        bullet_details: List[Dict[str, object]],
    ) -> Tuple[List[Dict[str, List[str]]], List[str]]:
        ordered = sorted(
            bullet_details,
            key=lambda item: (item.get("section_index", 0), item.get("bullet_index", 0)),
        )

        sections_map: Dict[Tuple[int, str], List[str]] = {}
        for detail in ordered:
            key = (detail.get("section_index", 0), detail.get("section", "Highlights"))
            sections_map.setdefault(key, []).append(detail.get("text", ""))

        structured_sections: List[Dict[str, List[str]]] = []
        flat_bullets: List[str] = []

        for (_, name), bullets in sections_map.items():
            cleaned = [text for text in bullets if text]
            if cleaned:
                structured_sections.append({"name": name, "bullets": cleaned})
                flat_bullets.extend(cleaned)

        return structured_sections, flat_bullets

    def _flatten_sections(self, sections: Sequence[Dict[str, List[str]]]) -> List[str]:
        bullets: List[str] = []
        for section in sections or []:
            bullets.extend(section.get("bullets", []))
        return bullets

    def _repair_json_string(self, s: str) -> str:
        """
        Attempt to repair common JSON issues from LLM output.
        Handles: unterminated strings, missing commas, trailing commas, etc.
        """
        import re
        
        # Remove any trailing incomplete content after last complete structure
        # Find the last proper closing brace
        brace_count = 0
        last_valid_close = -1
        in_string = False
        escape_next = False
        
        for i, char in enumerate(s):
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    last_valid_close = i
        
        if last_valid_close > 0 and last_valid_close < len(s) - 1:
            s = s[:last_valid_close + 1]
        
        # Fix trailing commas before ] or }
        s = re.sub(r',(\s*[\]\}])', r'\1', s)
        
        # Fix unterminated strings at end of object/array
        # Pattern: "key": "value[no closing quote]
        # This is tricky - try to find lines with odd number of quotes and fix
        lines = s.split('\n')
        fixed_lines = []
        for line in lines:
            # Count unescaped quotes
            quote_count = len(re.findall(r'(?<!\\)"', line))
            if quote_count % 2 == 1:
                # Odd quotes - likely unterminated string
                # Add closing quote before any trailing comma, ] or }
                line = re.sub(r'([^"\\])(\s*[,\]\}]?\s*)$', r'\1"\2', line)
            fixed_lines.append(line)
        s = '\n'.join(fixed_lines)
        
        return s

    def _call_openai_json(
        self,
        *,
        instructions: str,
        payload: Dict[str, Any],
        temperature: float,
        max_output_tokens: int,
        grounding: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], str, Dict[str, int]]:
        request_params: Dict[str, Any] = {
            "model": self.model,
            "instructions": instructions,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Return response in JSON format:\n\n{json.dumps(payload, ensure_ascii=True, indent=2)}",
                        }
                    ],
                }
            ],
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }

        # OpenAI doesn't allow web_search with JSON mode
        # When grounding is needed, use text mode and parse JSON manually
        if grounding:
            request_params["tools"] = [{"type": "web_search"}]
            # Skip JSON mode - model will return JSON in text format
        else:
            # Use strict JSON mode when web_search isn't needed
            request_params["text"] = {
                "format": {
                    "type": "json_object"
                }
            }

        try:
            response = self.client.responses.create(**request_params)
        except Exception as exc:  # noqa: BLE001
            raise TailoringPipelineError(f"OpenAI request failed: {exc}") from exc

        payload_dict = self._extract_response_json(response)
        usage = self._extract_usage(response)
        run_id = getattr(response, "id", "")
        return payload_dict, run_id, usage

    def _extract_response_json(self, response: Any) -> Dict[str, Any]:
        output_text_parts: List[str] = []
        for item in getattr(response, "output", []) or []:
            for block in getattr(item, "content", []) or []:
                if getattr(block, "type", None) == "output_text":
                    output_text_parts.append(getattr(block, "text", ""))

        raw_payload = "".join(output_text_parts).strip()

        # Clean various text prefixes that might appear before JSON
        # Common patterns: "Based on...", "Here is...", etc.
        if not raw_payload.startswith("{"):
            # Try to find where JSON actually starts
            json_start = raw_payload.find("{")
            if json_start > 0:
                # Check if there's explanatory text before the JSON
                prefix = raw_payload[:json_start].strip()
                if len(prefix) > 0 and len(prefix) < 200:  # Likely explanatory text
                    logger.warning(f"Stripping non-JSON prefix: {prefix[:100]}...")
                    raw_payload = raw_payload[json_start:]

        # Clean markdown code fences if present
        if raw_payload.startswith("```json"):
            raw_payload = raw_payload[7:]
        elif raw_payload.startswith("```"):
            raw_payload = raw_payload[3:]
        if raw_payload.endswith("```"):
            raw_payload = raw_payload[:-3]
        raw_payload = raw_payload.strip()

        # SDK convenience property fallback
        if not raw_payload and hasattr(response, "output_text"):
            raw_payload = (getattr(response, "output_text", "") or "").strip()

        if not raw_payload:
            raise TailoringPipelineError("Received empty response from OpenAI.")

        try:
            return json.loads(raw_payload)
        except json.JSONDecodeError as e:
            # Log the actual error and payload for debugging
            logger.error(
                f"JSON decode error at line {e.lineno} col {e.colno}: {e.msg}. "
                f"Payload preview: {raw_payload[:500]}..."
            )
            
            # Try aggressive extraction: find first { and last }
            start = raw_payload.find("{")
            end = raw_payload.rfind("}")
            
            if start == -1 or end == -1:
                raise TailoringPipelineError(
                    f"Failed to parse OpenAI JSON payload. Error: {e.msg} at line {e.lineno}"
                ) from e
            
            # Extract potential JSON
            potential_json = raw_payload[start : end + 1]
            
            try:
                return json.loads(potential_json)
            except json.JSONDecodeError as e2:
                # Try repairing the JSON
                try:
                    repaired = self._repair_json_string(potential_json)
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass
                
                # Last resort: Try to find JSON between markdown sections
                # Pattern: look for JSON after "**" markers or other markdown
                lines = raw_payload.split('\n')
                json_lines = []
                in_json = False
                brace_count = 0
                
                for line in lines:
                    stripped = line.strip()
                    if not in_json and stripped.startswith('{'):
                        in_json = True
                        brace_count = stripped.count('{') - stripped.count('}')
                        json_lines.append(line)
                    elif in_json:
                        json_lines.append(line)
                        brace_count += stripped.count('{') - stripped.count('}')
                        if brace_count == 0:
                            break
                
                if json_lines:
                    try:
                        potential_json = '\n'.join(json_lines)
                        return json.loads(potential_json)
                    except json.JSONDecodeError:
                        pass
                
                raise TailoringPipelineError(
                    f"Failed to parse extracted JSON. Original error: {e.msg}, "
                    f"Extraction error: {e2.msg}. The model returned narrative text instead of JSON. "
                    f"Check logs for full payload."
                ) from e2

    def _extract_usage(self, response: Any) -> Dict[str, int]:
        usage = getattr(response, "usage", None)
        if not usage:
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        prompt = getattr(usage, "input_tokens", 0)
        completion = getattr(usage, "output_tokens", 0)
        total = getattr(usage, "total_tokens", 0) or (prompt + completion)
        return {
            "prompt_tokens": int(prompt or 0),
            "completion_tokens": int(completion or 0),
            "total_tokens": int(total or 0),
        }

    def _merge_usage(self, accumulator: Dict[str, int], usage: Dict[str, int]) -> None:
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            accumulator[key] = accumulator.get(key, 0) + int(usage.get(key, 0) or 0)

    def _fetch_job_description_from_url(self, url: str) -> str:
        """
        Use OpenAI web search to fetch and extract job description from a URL.
        
        Args:
            url: Job posting URL to fetch
            
        Returns:
            Extracted job description text
        """
        extraction_payload = {
            "url": url,
            "instructions": [
                "Extract the complete job description including:",
                "- Job title and location",
                "- Job summary/overview",
                "- Key responsibilities and duties",
                "- Required qualifications and skills",
                "- Preferred qualifications and skills",
                "- Education requirements",
                "- Years of experience required",
                "- Any certifications or licenses needed",
                "- Company information (if available)",
            ]
        }
        
        instructions = (
            "You are a job posting extraction specialist. Use web search to fetch the job posting "
            "from the provided URL and extract ALL relevant information about the role.\n\n"
            "CRITICAL OUTPUT FORMAT REQUIREMENTS:\n"
            "- You MUST return ONLY a valid JSON object\n"
            "- DO NOT include any explanatory text before or after the JSON\n"
            "- START YOUR RESPONSE WITH THE { CHARACTER\n"
            "- END YOUR RESPONSE WITH THE } CHARACTER\n"
            "- If the website is blocked by CAPTCHA or unavailable, return:\n"
            '  {"error": "Website blocked or unavailable", "full_description": "", "job_title": "", "location": "", "company": ""}\n\n'
            "Required JSON structure:\n"
            "{\n"
            '  "job_title": "string - exact job title from posting",\n'
            '  "location": "string - job location",\n'
            '  "company": "string - company name",\n'
            '  "full_description": "string - Complete job description with all sections, responsibilities, and requirements",\n'
            '  "responsibilities": ["array of responsibility bullet points"],\n'
            '  "required_qualifications": ["array of required qualifications"],\n'
            '  "preferred_qualifications": ["array of preferred qualifications"],\n'
            '  "education": "string - education requirements",\n'
            '  "experience_years": "string - years of experience required"\n'
            "}"
        )
        
        grounding = {
            "type": "web_search",
            "web_search": {
                "queries": [f"job posting {url}"]
            },
        }
        
        try:
            response_payload, _run_id, _usage = self._call_openai_json(
                instructions=instructions,
                payload=extraction_payload,
                temperature=0.0,
                max_output_tokens=2000,
                grounding=grounding,
            )
            
            # Check for error responses (CAPTCHA, blocked sites, etc.)
            if response_payload.get("error"):
                logger.warning(f"Web search encountered error: {response_payload.get('error')}")
                return ""
            
            # Check if we got meaningful content
            full_desc = response_payload.get("full_description", "")
            if not full_desc or len(full_desc) < 100:
                # Try to construct from parts if full_description is missing
                parts = []
                if response_payload.get("responsibilities"):
                    parts.extend(response_payload["responsibilities"])
                if response_payload.get("required_qualifications"):
                    parts.extend(response_payload["required_qualifications"])
                
                if parts:
                    full_desc = "\n".join(parts)
            
            if not full_desc or len(full_desc) < 50:
                logger.warning(f"Web search returned minimal/no content for {url}")
                return ""
            
            # Construct full description from extracted parts
            full_desc_parts = []
            
            if response_payload.get("job_title"):
                full_desc_parts.append(f"Job Title: {response_payload['job_title']}")
            if response_payload.get("location"):
                full_desc_parts.append(f"Location: {response_payload['location']}")
            if response_payload.get("company"):
                full_desc_parts.append(f"Company: {response_payload['company']}")
            
            if response_payload.get("full_description"):
                full_desc_parts.append(response_payload["full_description"])
            
            if response_payload.get("responsibilities"):
                full_desc_parts.append("\nResponsibilities:")
                for resp in response_payload["responsibilities"]:
                    full_desc_parts.append(f"- {resp}")
            
            if response_payload.get("required_qualifications"):
                full_desc_parts.append("\nRequired Qualifications:")
                for qual in response_payload["required_qualifications"]:
                    full_desc_parts.append(f"- {qual}")
            
            if response_payload.get("preferred_qualifications"):
                full_desc_parts.append("\nPreferred Qualifications:")
                for qual in response_payload["preferred_qualifications"]:
                    full_desc_parts.append(f"- {qual}")
            
            if response_payload.get("education"):
                full_desc_parts.append(f"\nEducation: {response_payload['education']}")
            if response_payload.get("experience_years"):
                full_desc_parts.append(f"Experience: {response_payload['experience_years']}")
            
            full_description = "\n".join(full_desc_parts)
            
            if not full_description or len(full_description) < 100:
                logger.warning(f"Web search returned minimal content for {url}: {len(full_description)} chars")
                return ""
            
            logger.info(f"Successfully extracted {len(full_description)} chars from {url}")
            return full_description
            
        except Exception as e:
            logger.error(f"Failed to fetch job description from {url}: {e}")
            return ""

class ResumeOptimizer:
    """
    Helper class for ATS optimization and resume quality validation.
    """

    @staticmethod
    def calculate_ats_score(
        bullet_points: List[str], 
        job_keywords: List[str],
        required_skills: Optional[List[str]] = None,
        preferred_skills: Optional[List[str]] = None,
    ) -> Dict[str, object]:
        """
        Calculate comprehensive ATS compatibility score with detailed breakdown.
        
        Returns:
            - overall_score: 0-100 weighted score
            - keyword_match: % of job keywords found
            - required_skills_match: % of required skills found
            - preferred_skills_match: % of preferred skills found
            - missing_critical: List of missing required keywords
            - missing_preferred: List of missing preferred keywords
            - suggestions: Actionable recommendations
        """
        if not job_keywords and not required_skills:
            return {
                "overall_score": 0.0,
                "keyword_match": 0.0,
                "required_skills_match": 0.0,
                "preferred_skills_match": 0.0,
                "missing_critical": [],
                "missing_preferred": [],
                "suggestions": ["No job requirements provided for analysis"],
            }

        resume_text = " ".join(bullet_points).lower()
        
        # Calculate keyword match
        keyword_matches = 0
        matched_keywords = []
        if job_keywords:
            for kw in job_keywords:
                if kw.lower() in resume_text:
                    keyword_matches += 1
                    matched_keywords.append(kw)
            keyword_match_pct = (keyword_matches / len(job_keywords)) * 100
        else:
            keyword_match_pct = 0.0
        
        # Calculate required skills match (weighted heavily)
        required_matches = 0
        missing_required = []
        matched_required = []
        if required_skills:
            for skill in required_skills:
                # Skip single-letter or overly generic terms that provide no value
                if len(skill) <= 2 or skill.lower() in ['a', 'an', 'the', 'aid', 'it', 'is']:
                    continue
                if skill.lower() in resume_text:
                    required_matches += 1
                    matched_required.append(skill)
                else:
                    missing_required.append(skill)
            # Recalculate with filtered skills
            total_valid_required = required_matches + len(missing_required)
            if total_valid_required > 0:
                required_match_pct = (required_matches / total_valid_required) * 100
            else:
                required_match_pct = 100.0
        else:
            required_match_pct = 100.0  # No requirements = perfect score
        
        # Calculate preferred skills match (bonus points)
        preferred_matches = 0
        missing_preferred = []
        matched_preferred = []
        if preferred_skills:
            for skill in preferred_skills:
                # Skip trivial terms
                if len(skill) <= 2 or skill.lower() in ['a', 'an', 'the', 'aid', 'it', 'is']:
                    continue
                if skill.lower() in resume_text:
                    preferred_matches += 1
                    matched_preferred.append(skill)
                else:
                    missing_preferred.append(skill)
            total_valid_preferred = preferred_matches + len(missing_preferred)
            if total_valid_preferred > 0:
                preferred_match_pct = (preferred_matches / total_valid_preferred) * 100
            else:
                preferred_match_pct = 0.0
        else:
            preferred_match_pct = 0.0
        
        # Weighted overall score
        # Required skills: 60%, Keyword match: 30%, Preferred skills: 10%
        overall_score = (
            (required_match_pct * 0.60) +
            (keyword_match_pct * 0.30) +
            (preferred_match_pct * 0.10)
        )
        
        # Generate specific, actionable suggestions
        suggestions = []
        
        # Focus on critical missing skills first
        if missing_required and len(missing_required) > 0:
            top_missing = missing_required[:3]
            if len(top_missing) == 1:
                suggestions.append(
                    f"Add required skill: {top_missing[0]} - Include specific examples of how you've used this in your experience"
                )
            else:
                suggestions.append(
                    f"Add required skills: {', '.join(top_missing)} - Weave these into your achievement descriptions with concrete examples"
                )
        
        # Provide context-aware keyword suggestions
        if keyword_match_pct < 60 and job_keywords:
            missing_keywords = [kw for kw in job_keywords if kw.lower() not in resume_text][:5]
            if missing_keywords:
                suggestions.append(
                    f"Strengthen keyword coverage by incorporating: {', '.join(missing_keywords)} - Use these terms naturally when describing relevant work"
                )
        
        # Suggest preferred skills if space allows
        if missing_preferred and preferred_match_pct < 40 and len(missing_preferred) > 0:
            top_preferred = [s for s in missing_preferred[:3] if len(s) > 2]
            if top_preferred:
                suggestions.append(
                    f"Consider highlighting: {', '.join(top_preferred)} - These preferred skills could differentiate your application"
                )
        
        # Provide overall guidance
        if overall_score >= 85:
            suggestions.append(
                "Strong ATS compatibility - Your resume aligns well with job requirements"
            )
        elif overall_score >= 70:
            suggestions.append(
                "Good foundation - Focus on incorporating the missing required skills to reach excellent ATS compatibility"
            )
        elif overall_score >= 50:
            suggestions.append(
                "Moderate ATS match - Priority: add required skills with specific examples from your experience"
            )
        else:
            suggestions.append(
                "Significant gaps in required skills - Review job posting carefully and align your resume with key requirements"
            )
        
        # Add metric-focused suggestion if few numbers detected
        numbers_count = len(re.findall(r'\d+', resume_text))
        if numbers_count < len(bullet_points) * 0.5:  # Less than 50% of bullets have metrics
            suggestions.append(
                "Add quantifiable metrics to your achievements (e.g., percentages, dollar amounts, time savings, user scale)"
            )
        
        return {
            "overall_score": round(overall_score, 1),
            "keyword_match": round(keyword_match_pct, 1),
            "required_skills_match": round(required_match_pct, 1),
            "preferred_skills_match": round(preferred_match_pct, 1),
            "missing_critical": missing_required[:10],  # Limit to top 10
            "missing_preferred": missing_preferred[:10],
            "matched_required": matched_required,
            "matched_preferred": matched_preferred,
            "suggestions": suggestions,
        }

    @staticmethod
    def enhance_bullet_with_metrics(bullet: str) -> str:
        """
        Enhance a bullet point by emphasizing metrics and results.
        """
        has_number = bool(re.search(r"\d+", bullet))
        has_percent = bool(re.search(r"\d+%", bullet))

        if has_number or has_percent:
            return bullet

        return f"{bullet} [Add metrics: X%, $Y, Z units]"

    @staticmethod
    def validate_bullet_point(bullet: str) -> Dict[str, object]:
        """
        Validate bullet point against ATS and recruiter best practices.
        """
        issues = []
        suggestions = []
        
        # ATS-critical checks
        action_verbs = {
            "led", "managed", "developed", "created", "improved", "increased",
            "reduced", "achieved", "delivered", "built", "designed", "implemented",
            "analyzed", "optimized", "launched", "coordinated", "established",
        }
        
        first_word = bullet.split()[0].lower().rstrip(".,;:") if bullet else ""
        
        # Length check (ATS systems may truncate)
        if len(bullet) > 220:
            issues.append("Bullet exceeds 220 characters - may be truncated by ATS")
            suggestions.append("Aim for 100-180 characters for optimal ATS parsing")
        elif len(bullet) < 50:
            issues.append("Bullet is too short - may lack detail")
            suggestions.append("Expand with specific metrics and outcomes")

        # Action verb check (critical for ATS)
        if not re.match(r"^[A-Z]", bullet):
            issues.append("Must start with capital letter for ATS parsing")
            suggestions.append("Capitalize the first word")
        
        if first_word not in action_verbs:
            issues.append("Should start with strong action verb for ATS scoring")
            suggestions.append(
                f"Start with: {', '.join(list(action_verbs)[:5])}, etc."
            )

        # Metrics check (recruiter appeal)
        has_number = bool(re.search(r"\d+", bullet))
        has_percent = bool(re.search(r"\d+%", bullet))
        has_dollar = bool(re.search(r"\$[\d,]+", bullet))
        
        if not (has_number or has_percent or has_dollar):
            suggestions.append("Add quantifiable metrics (%, $, numbers)")
        
        # Keyword density check
        if len(bullet.split()) < 10:
            suggestions.append("Add more context and keywords")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "suggestions": suggestions,
            "has_metrics": has_number or has_percent or has_dollar,
            "starts_with_action_verb": first_word in action_verbs,
            "character_count": len(bullet),
        }
