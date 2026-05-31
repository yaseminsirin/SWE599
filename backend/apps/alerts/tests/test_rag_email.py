from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.alerts.models import JobAlert
from apps.alerts.services.matching import _send_alert_email, process_job_alerts
from apps.alerts.services.rag.email_generation import (
    AlertEmailContent,
    build_alert_job_url,
    build_fallback_content,
    compose_alert_email_body,
    generate_alert_email_content,
)
from apps.alerts.services.rag.job_context import parse_llm_response
from apps.alerts.services.rag.llm.gemini_provider import GeminiLLMProvider
from apps.jobs.models import JobPosting

_TECH_DESC = (
    "Python backend developer building REST APIs, Django services, and cloud deployments. "
    "Requires Python, SQL, and distributed systems experience."
)


class RagEmailGenerationTests(TestCase):
    def setUp(self):
        self.alert = JobAlert.objects.create(
            name="Backend roles",
            keyword="python backend",
            is_remote=True,
            is_active=True,
            notify_email="alerts@example.com",
        )
        self.job = JobPosting.objects.create(
            source="adzuna",
            source_job_id="rag-1",
            title="Python Backend Engineer",
            company_name="Acme",
            description_clean=_TECH_DESC,
            job_url="https://example.com/rag-1",
            location_text="Remote, US",
            is_remote=True,
            employment_type="full_time",
            content_hash="rag-h1",
            posted_at=timezone.now(),
            normalized_at=timezone.now(),
        )

    @override_settings(
        LLM_PROVIDER="gemini",
        LLM_MODEL="gemini-2.0-flash",
        GEMINI_API_KEY="test-gemini-key",
    )
    def test_gemini_provider_reads_settings(self):
        provider = GeminiLLMProvider()
        self.assertTrue(provider.is_available())
        self.assertEqual(provider.model, "gemini-2.0-flash")
        self.assertEqual(provider.api_key, "test-gemini-key")

    def test_parse_llm_response_highlights_sections(self):
        raw = (
            "EXPLANATION:\n"
            "These roles match backend Python interests.\n\n"
            "HIGHLIGHTS:\n"
            "- Python Backend Engineer at Acme\n"
            "- Remote-friendly backend work\n"
        )
        explanation, bullets = parse_llm_response(raw)
        self.assertIn("backend Python", explanation)
        self.assertEqual(len(bullets), 2)

    def test_parse_rejects_exaggerated_explanation(self):
        raw = (
            "EXPLANATION:\n"
            "This is your perfect match for a dream job.\n\n"
            "HIGHLIGHTS:\n"
            "- Great role\n"
        )
        explanation, bullets = parse_llm_response(raw)
        self.assertEqual(explanation, "")
        self.assertEqual(len(bullets), 1)

    @override_settings(LLM_PROVIDER="")
    def test_fallback_when_provider_not_configured(self):
        content = generate_alert_email_content(self.alert, [self.job])
        self.assertFalse(content.used_rag)
        self.assertIn("software/tech", content.explanation.lower())

    def test_successful_rag_generation(self):
        mock_provider = MagicMock()
        mock_provider.provider_name = "openai"
        mock_provider.is_available.return_value = True
        mock_provider.generate.return_value = (
            "EXPLANATION:\n"
            "These jobs were selected because they match Python backend and remote preferences.\n\n"
            "HIGHLIGHTS:\n"
            "- Python Backend Engineer at Acme (remote-friendly)\n"
        )

        with patch(
            "apps.alerts.services.rag.email_generation.get_llm_provider",
            return_value=mock_provider,
        ):
            content = generate_alert_email_content(self.alert, [self.job])

        self.assertTrue(content.used_rag)
        self.assertEqual(content.provider, "openai")
        self.assertIn("Python backend", content.explanation)
        self.assertGreaterEqual(len(content.job_bullets), 1)

    def test_provider_failure_falls_back(self):
        mock_provider = MagicMock()
        mock_provider.provider_name = "openai"
        mock_provider.is_available.return_value = True
        mock_provider.generate.side_effect = RuntimeError("API down")

        with patch(
            "apps.alerts.services.rag.email_generation.get_llm_provider",
            return_value=mock_provider,
        ):
            content = generate_alert_email_content(self.alert, [self.job])

        self.assertFalse(content.used_rag)
        fallback = build_fallback_content(self.alert, [self.job])
        self.assertEqual(content.explanation, fallback.explanation)

    @override_settings(
        BREVO_API_KEY="test-brevo-key",
        DEFAULT_FROM_EMAIL="alerts@example.com",
        SITE_URL="http://localhost:8000",
    )
    @patch("apps.alerts.services.matching.send_transactional_email")
    def test_alert_email_uses_tracking_links(self, mock_brevo):
        mock_brevo.return_value = {"messageId": "test-id"}
        mock_provider = MagicMock()
        mock_provider.provider_name = "gemini"
        mock_provider.is_available.return_value = True
        mock_provider.generate.return_value = (
            "EXPLANATION:\n"
            "These jobs align with your Python backend alert.\n\n"
            "HIGHLIGHTS:\n"
            "- Acme — Python Backend Engineer\n"
        )

        with patch(
            "apps.alerts.services.rag.email_generation.get_llm_provider",
            return_value=mock_provider,
        ):
            meta = _send_alert_email(self.alert, [self.job], recipient="alerts@example.com")

        self.assertTrue(meta["used_rag"])
        mock_brevo.assert_called_once()
        call_kwargs = mock_brevo.call_args.kwargs
        body = call_kwargs["body"]
        self.assertIn("Python backend alert", body)
        self.assertIn("Matching jobs:", body)
        expected_url = build_alert_job_url(alert=self.alert, job=self.job)
        self.assertIn(expected_url, body)
        self.assertNotIn("https://example.com/rag-1", body)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_fallback_email_includes_job_links(self):
        content = build_fallback_content(self.alert, [self.job])
        body = compose_alert_email_body(content, [self.job], alert=self.alert)
        self.assertIn("Matching jobs:", body)
        self.assertIn("Python Backend Engineer", body)
        self.assertIn("/api/tracking/alert-click/", body)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    @patch("apps.alerts.services.matching.send_transactional_email")
    @patch("apps.alerts.services.matching.retrieve_alert_jobs")
    def test_process_job_alerts_never_fails_on_llm_error(self, mock_retrieve, mock_brevo):
        mock_retrieve.return_value = [self.job]
        mock_brevo.return_value = {"messageId": "test-id"}
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.generate.side_effect = RuntimeError("provider unavailable")

        with patch(
            "apps.alerts.services.rag.email_generation.get_llm_provider",
            return_value=mock_provider,
        ):
            summary = process_job_alerts(max_results_per_alert=20)

        self.assertEqual(summary["alerts_notified"], 1)
        self.assertEqual(summary["fallback_emails"], 1)
        self.assertEqual(summary["rag_emails"], 0)
        mock_brevo.assert_called_once()
