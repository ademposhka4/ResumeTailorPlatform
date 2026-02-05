from types import SimpleNamespace
from unittest import mock

from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from jobs.frontend_views import job_create


@override_settings(
    SESSION_ENGINE='django.contrib.sessions.backends.cache',
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    },
)
class JobFrontendViewsTests(SimpleTestCase):
    """Unit tests for job creation flow without hitting the database."""

    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user = SimpleNamespace(
            is_authenticated=True,
            tokens_available=100,
            username="testing_user",
        )

    def _build_request(self, data: dict):
        request = self.factory.post(reverse("job_create"), data)
        request.user = self.user

        # Attach session and messages for the view logic.
        session_middleware = SessionMiddleware(lambda r: None)
        session_middleware.process_request(request)
        request.session.save()

        MessageMiddleware(lambda r: None).process_request(request)
        return request

    def test_job_create_requires_url_or_description(self) -> None:
        request = self._build_request(
            {
                "title": "Backend Engineer",
                "company": "Acme Co",
            }
        )

        response = job_create(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("job_create"))

        messages = [str(message) for message in request._messages]
        self.assertTrue(
            any("Provide either a job description" in message for message in messages)
        )

    @mock.patch("jobs.frontend_views.JobPosting.objects.create")
    def test_job_create_with_raw_description_only(self, mock_create) -> None:
        mock_job = mock.Mock()
        mock_job.id = 42
        mock_job.title = "Backend Engineer"
        mock_job.company = "Acme Co"
        mock_create.return_value = mock_job

        request = self._build_request(
            {
                "title": "Backend Engineer",
                "company": "Acme Co",
                "raw_description": "Write APIs and data pipelines.",
            }
        )

        response = job_create(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("job_detail", kwargs={"job_id": 42}))

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        self.assertEqual(call_kwargs["raw_description"], "Write APIs and data pipelines.")
        self.assertEqual(call_kwargs["source_url"], "")
        self.assertIs(call_kwargs["user"], self.user)

    @mock.patch("jobs.frontend_views.JobPosting.objects.create")
    def test_job_create_with_url_only(self, mock_create) -> None:
        mock_job = mock.Mock()
        mock_job.id = 7
        mock_job.title = "Backend Engineer"
        mock_job.company = "Acme Co"
        mock_create.return_value = mock_job

        request = self._build_request(
            {
                "title": "Backend Engineer",
                "company": "Acme Co",
                "source_url": "https://example.com/job/backend",
            }
        )

        response = job_create(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("job_detail", kwargs={"job_id": 7}))

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        self.assertEqual(call_kwargs["source_url"], "https://example.com/job/backend")
        self.assertEqual(call_kwargs["raw_description"], "")
