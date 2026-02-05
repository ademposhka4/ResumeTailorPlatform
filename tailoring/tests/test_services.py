from django.test import SimpleTestCase

from tailoring.services import AgentKitTailoringService


class AgentKitTailoringServiceTests(SimpleTestCase):
    """Unit tests for utility helpers that do not hit the OpenAI API."""

    def test_normalize_parameters_defaults(self) -> None:
        params = AgentKitTailoringService.normalize_parameters({})
        self.assertGreaterEqual(params["bullets_per_section"], 1)
        self.assertIsInstance(params["sections"], list)
        self.assertTrue(params["tone"])
        self.assertIn("temperature", params)

    def test_normalize_parameters_custom_values(self) -> None:
        params = AgentKitTailoringService.normalize_parameters(
            {
                "sections": "Results\nLeadership",
                "bullets_per_section": "4",
                "temperature": "0.65",
                "tone": "story-driven and persuasive",
                "include_summary": False,
                "include_cover_letter": True,
            }
        )
        self.assertEqual(params["sections"], ["Results", "Leadership"])
        self.assertEqual(params["bullets_per_section"], 4)
        self.assertAlmostEqual(params["temperature"], 0.65)
        self.assertFalse(params["include_summary"])
        self.assertTrue(params["include_cover_letter"])

    def test_normalize_parameters_stretch_and_layout(self) -> None:
        params = AgentKitTailoringService.normalize_parameters(
            {
                "stretch_level": "5",
                "section_layout": "Professional Experience, Leadership, Projects",
                "cover_letter_inserts": "Hackathon win\nDean's List",
            }
        )
        self.assertEqual(params["stretch_level"], 3)
        self.assertEqual(
            params["section_layout"],
            ["Professional Experience", "Leadership", "Projects"],
        )
        self.assertEqual(
            params["cover_letter_inserts"],
            ["Hackathon win", "Dean's List"],
        )

    def test_collect_experience_snippets_prefers_matching_skills(self) -> None:
        service = AgentKitTailoringService()
        job_description = """
        Responsibilities:
        - Develop data pipelines using Python and SQL.
        - Lead cross-functional automation initiatives.
        Requirements:
        - Python, SQL, Automation
        """
        requirements = service._extract_job_requirements(job_description)
        job_profile = service._build_job_profile(
            job_description=job_description,
            requirements=requirements,
            source_url="",
        )

        experience_graph = {
            "experiences": [
                {
                    "id": "exp-1",
                    "type": "work",
                    "title": "Data Automation Analyst",
                    "company": "TechCorp",
                    "start_date": "2023",
                    "current": True,
                    "skills": ["Python", "SQL", "Automation"],
                    "achievements": [
                        "Automated data pipeline that reduced processing time by 40%",
                        "Built SQL validation suite improving data quality by 25%",
                    ],
                },
                {
                    "id": "exp-2",
                    "type": "project",
                    "title": "Marketing Website Redesign",
                    "skills": ["Figma", "Copywriting"],
                    "achievements": ["Led redesign increasing conversions by 10%"],
                },
            ]
        }

        selected = service._collect_experience_snippets(
            experience_graph=experience_graph,
            job_profile=job_profile,
            limit_per_bucket=3,
        )

        self.assertIn("Professional Experience", selected)
        self.assertEqual(len(selected["Professional Experience"]), 1)
        self.assertEqual(selected["Professional Experience"][0].snippet_id, "exp-1")
