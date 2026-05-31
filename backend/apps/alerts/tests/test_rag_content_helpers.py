from django.test import TestCase
from django.utils import timezone

from apps.alerts.services.rag.content_helpers import (
    MIN_SIGNALS_TO_SHOW,
    build_fallback_reason,
    clean_ai_signal,
    derive_taxonomy_signals,
    filter_key_signals,
    is_quality_signal,
    match_taxonomy_signals,
    sanitize_ai_summary,
)
from apps.alerts.services.rag.job_context import parse_llm_response, validate_llm_email_payload
from apps.jobs.models import JobPosting

_DATA_ANALYST_DESC = (
    "Lead data analysis and reporting for business systems. Build performance metrics dashboards, "
    "support decision support workflows, and collaborate with stakeholders on analytical reporting."
)

_BACKEND_DESC = (
    "Python backend developer building REST APIs, Django microservices, and cloud deployments. "
    "Requires Python, SQL, distributed systems, and API design experience."
)

_PM_DESC = (
    "Product manager owning product strategy, roadmap planning, stakeholder communication, "
    "and data-informed agile product development across cross-functional teams."
)


class ContentHelpersTests(TestCase):
    _counter = 0

    def _job(self, **kwargs) -> JobPosting:
        ContentHelpersTests._counter += 1
        n = ContentHelpersTests._counter
        defaults = {
            "source": "adzuna",
            "source_job_id": f"t-{n}",
            "title": "Data Analyst",
            "company_name": "Acme Agency",
            "description_clean": _DATA_ANALYST_DESC,
            "job_url": f"https://example.com/{n}",
            "location_text": "Remote",
            "is_remote": True,
            "employment_type": "full_time",
            "content_hash": f"h-{n}",
            "posted_at": timezone.now(),
            "normalized_at": timezone.now(),
        }
        defaults.update(kwargs)
        return JobPosting.objects.create(**defaults)

    def test_rejects_garbage_signals(self):
        for phrase in (
            "Position",
            "Position Is",
            "In Support Of",
            "analyst systems analyst western",
            "agency button below to",
            "admin operations position is",
        ):
            self.assertIsNone(clean_ai_signal(phrase), phrase)

    def test_accepts_taxonomy_style_phrases(self):
        for phrase in (
            "Data analysis and reporting",
            "API and backend development",
            "Product roadmap ownership",
        ):
            self.assertTrue(is_quality_signal(phrase), phrase)

    def test_accepts_technology_single_words(self):
        self.assertTrue(is_quality_signal("Python"))
        self.assertTrue(is_quality_signal("SQL"))

    def test_filter_key_signals_removes_noise(self):
        raw = ["Position Is", "Data analysis and reporting", "Located", "Performance metrics"]
        filtered = filter_key_signals(raw)
        self.assertNotIn("Position Is", filtered)
        self.assertNotIn("Located", filtered)
        self.assertIn("Data analysis and reporting", filtered)

    def test_data_analyst_taxonomy_signals(self):
        jobs = [
            self._job(source_job_id="da-1"),
            self._job(source_job_id="da-2", title="Senior Data Analyst"),
        ]
        signals = derive_taxonomy_signals(jobs, query="data analyst")
        self.assertGreaterEqual(len(signals), MIN_SIGNALS_TO_SHOW)
        joined = " ".join(signals).lower()
        self.assertTrue(any(term in joined for term in ("data analysis", "reporting", "performance metrics")))

    def test_backend_developer_taxonomy_signals(self):
        job = self._job(
            source_job_id="be-1",
            title="Python Backend Engineer",
            description_clean=_BACKEND_DESC,
        )
        signals = derive_taxonomy_signals([job], query="backend developer")
        joined = " ".join(signals).lower()
        self.assertTrue(any(term in joined for term in ("python", "api development", "backend services")))

    def test_product_manager_taxonomy_signals(self):
        job = self._job(
            source_job_id="pm-1",
            title="Product Manager",
            description_clean=_PM_DESC,
        )
        signals = derive_taxonomy_signals([job], query="product manager")
        joined = " ".join(signals).lower()
        self.assertTrue(any(term in joined for term in ("product strategy", "roadmap", "stakeholder")))

    def test_build_fallback_reason_with_signals(self):
        job = self._job()
        reason = build_fallback_reason(
            job,
            "data analyst",
            ["Data analysis and reporting", "Performance metrics"],
        )
        self.assertIn("data analyst", reason.lower())
        self.assertIn("data analysis", reason.lower())
        self.assertNotIn("position is", reason.lower())

    def test_build_fallback_reason_without_signals(self):
        job = self._job()
        reason = build_fallback_reason(job, "data analyst", ["Reporting"])
        self.assertIn("similarity between the alert query", reason.lower())

    def test_sanitize_ai_summary_rejects_garbage(self):
        self.assertIsNone(sanitize_ai_summary("These listings share recurring themes across title and company."))
        self.assertIsNone(sanitize_ai_summary("position is located in support of management program"))

    def test_sanitize_ai_summary_accepts_quality_text(self):
        text = (
            "These roles align with your data analyst alert because they emphasize analytical reporting, "
            "performance metrics, and business systems analysis across public-sector teams."
        )
        self.assertIsNotNone(sanitize_ai_summary(text))

    def test_parse_llm_json_validates_and_filters(self):
        job = self._job()
        raw = f"""{{
          "summary": "These roles align with your data analyst alert because they emphasize analytical reporting, performance evaluation, and business systems analysis across matched listings.",
          "key_signals": [
            "Data analysis and reporting",
            "Business systems analysis",
            "Performance metrics",
            "Position Is"
          ],
          "job_reasons": {{
            "{job.id}": "This role fits your data analyst alert because it focuses on performance reporting, business systems analysis, and data-driven decision support."
          }}
        }}"""
        parsed = parse_llm_response(raw, jobs=[job])
        self.assertTrue(parsed.is_valid)
        self.assertIn("data analyst", parsed.summary.lower())
        self.assertGreaterEqual(len(parsed.key_signals), MIN_SIGNALS_TO_SHOW)
        self.assertTrue(all(is_quality_signal(s) for s in parsed.key_signals))
        self.assertNotIn("Position Is", parsed.key_signals)
        self.assertIn(str(job.id), parsed.job_reasons)

    def test_validate_llm_rejects_insufficient_signals(self):
        job = self._job()
        parsed = validate_llm_email_payload(
            {
                "summary": "",
                "key_signals": ["Python", "SQL"],
                "job_reasons": {},
            },
            [job],
        )
        self.assertFalse(parsed.is_valid)

    def test_match_taxonomy_never_returns_ngrams(self):
        haystack = (
            "Position is located in support of admin operations. "
            "Click on the agency button below to learn more about applicants."
        )
        signals = match_taxonomy_signals(haystack)
        for signal in signals:
            self.assertNotIn("position is", signal.lower())
