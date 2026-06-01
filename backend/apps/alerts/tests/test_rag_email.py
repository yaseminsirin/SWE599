from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.alerts.models import JobAlert
from apps.alerts.services.matching import _send_alert_email, process_job_alerts
from apps.alerts.services.rag.content_helpers import MIN_SIGNALS_TO_SHOW, is_quality_signal
from apps.alerts.services.rag.email_generation import (
    build_alert_apply_url,
    build_alert_job_url,
    build_alert_subject,
    build_fallback_content,
    compose_alert_email,
    generate_alert_email_content,
)
from apps.alerts.services.rag.llm.gemini_provider import GeminiLLMProvider
from apps.jobs.models import JobPosting

_TECH_DESC = (
    "Python backend developer building REST APIs, Django services, and cloud deployments. "
    "Requires Python, SQL, and distributed systems experience."
)


def _json_llm_response(job_id: int) -> str:
    return f"""{{
      "summary": "These roles align with your backend developer alert because they emphasize API development, Python backend services, and distributed systems engineering across the matched listings.",
      "key_signals": [
        "API and backend development",
        "Python backend services",
        "Distributed systems engineering"
      ],
      "job_reasons": {{
        "{job_id}": "This role fits your backend developer alert because it focuses on Python REST APIs and Django backend services at Acme."
      }}
    }}"""


class RagEmailGenerationTests(TestCase):
    def setUp(self):
        self.alert = JobAlert.objects.create(
            name="Backend roles",
            keyword="backend developer",
            is_remote=True,
            is_active=True,
            notify_email="alerts@example.com",
            filters={"search_mode": "semantic"},
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

    @override_settings(LLM_PROVIDER="")
    def test_fallback_hides_ai_sections_without_llm(self):
        content = generate_alert_email_content(self.alert, [self.job])
        self.assertFalse(content.used_rag)
        self.assertFalse(content.show_summary)
        self.assertNotIn("share recurring themes", (content.summary or "").lower())
        if content.show_key_signals:
            self.assertGreaterEqual(len(content.key_signals), MIN_SIGNALS_TO_SHOW)
            for signal in content.key_signals:
                self.assertTrue(is_quality_signal(signal), signal)

    def test_successful_rag_generation_json(self):
        mock_provider = MagicMock()
        mock_provider.provider_name = "openai"
        mock_provider.is_available.return_value = True
        mock_provider.generate.return_value = _json_llm_response(self.job.id)

        with patch(
            "apps.alerts.services.rag.email_generation.get_llm_provider",
            return_value=mock_provider,
        ):
            content = generate_alert_email_content(self.alert, [self.job])

        self.assertTrue(content.used_rag)
        self.assertTrue(content.show_summary)
        self.assertTrue(content.show_key_signals)
        self.assertIn("backend developer", content.summary.lower())
        self.assertGreaterEqual(len(content.key_signals), MIN_SIGNALS_TO_SHOW)
        self.assertTrue(all(is_quality_signal(s) for s in content.key_signals))
        self.assertIn("backend developer", content.job_match_notes[0].lower())
        provider_call = mock_provider.generate.call_args.kwargs
        self.assertIn(f"Required job_ids for job_reasons (all required): {self.job.id}", provider_call["user"])

    def test_provider_failure_falls_back_without_ai_insight(self):
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
        self.assertFalse(content.show_summary)
        fallback = build_fallback_content(self.alert, [self.job])
        self.assertEqual(content.show_key_signals, fallback.show_key_signals)

    def test_subject_format(self):
        subject = build_alert_subject(self.alert, 6)
        self.assertEqual(subject, "JobSense AI Alert: backend developer — 6 relevant matches")

    @override_settings(
        BREVO_API_KEY="test-brevo-key",
        DEFAULT_FROM_EMAIL="alerts@example.com",
        SITE_URL="http://localhost:8000",
    )
    @patch("apps.alerts.services.matching.send_transactional_email")
    def test_alert_email_hides_garbage_and_uses_direct_listing_url(self, mock_brevo):
        mock_brevo.return_value = {"messageId": "test-id"}
        mock_provider = MagicMock()
        mock_provider.provider_name = "gemini"
        mock_provider.is_available.return_value = True
        mock_provider.generate.return_value = _json_llm_response(self.job.id)

        with patch(
            "apps.alerts.services.rag.email_generation.get_llm_provider",
            return_value=mock_provider,
        ):
            meta = _send_alert_email(self.alert, [self.job], recipient="alerts@example.com")

        self.assertTrue(meta["used_rag"])
        call_kwargs = mock_brevo.call_args.kwargs
        self.assertNotIn("position is", call_kwargs["html_body"].lower())
        expected_url = build_alert_apply_url(alert=self.alert, job=self.job)
        self.assertIn(expected_url, call_kwargs["html_body"])
        self.assertNotIn(build_alert_job_url(alert=self.alert, job=self.job), call_kwargs["html_body"])
        self.assertIn('target="_blank"', call_kwargs["html_body"])

    def test_fallback_email_has_no_garbage_phrases(self):
        content = build_fallback_content(self.alert, [self.job])
        text_body, html_body = compose_alert_email(content, [self.job], alert=self.alert)
        self.assertIn("Matching Jobs", text_body)
        self.assertNotIn("position is", html_body.lower())
        self.assertNotIn("search_mode", html_body)
        if content.show_summary:
            self.fail("Fallback should not show AI summary section")

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
        mock_brevo.assert_called_once()
