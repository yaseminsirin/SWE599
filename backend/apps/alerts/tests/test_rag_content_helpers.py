from django.test import TestCase
from django.utils import timezone

from apps.alerts.services.rag.content_helpers import (
    derive_fallback_job_reason,
    derive_fallback_signals,
    derive_fallback_summary,
    filter_key_signals,
    is_quality_signal,
)
from apps.alerts.services.rag.job_context import parse_llm_response
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

    def test_rejects_meaningless_single_word_signals(self):
        for word in ("Position", "Located", "Management", "Data", "Program"):
            self.assertFalse(is_quality_signal(word))

    def test_accepts_meaningful_phrases(self):
        for phrase in (
            "Data analysis and reporting",
            "Business intelligence dashboards",
            "SQL-based analytical work",
            "API and backend development",
            "Product roadmap ownership",
        ):
            self.assertTrue(is_quality_signal(phrase), phrase)

    def test_accepts_technology_single_words(self):
        self.assertTrue(is_quality_signal("Python"))
        self.assertTrue(is_quality_signal("SQL"))

    def test_filter_key_signals_removes_noise(self):
        raw = ["Position", "Data analysis and reporting", "Located", "Performance metrics"]
        filtered = filter_key_signals(raw)
        self.assertNotIn("Position", filtered)
        self.assertNotIn("Located", filtered)
        self.assertIn("Data analysis and reporting", filtered)

    def test_data_analyst_fallback_signals_are_phrases(self):
        jobs = [
            self._job(source_job_id="da-1"),
            self._job(source_job_id="da-2", title="Senior Data Analyst"),
        ]
        signals = derive_fallback_signals(jobs, query="data analyst")
        self.assertGreaterEqual(len(signals), 1)
        for signal in signals:
            self.assertTrue(is_quality_signal(signal), signal)
            self.assertGreater(len(signal.split()), 1)

    def test_backend_developer_fallback_signals(self):
        job = self._job(
            source_job_id="be-1",
            title="Python Backend Engineer",
            description_clean=_BACKEND_DESC,
        )
        signals = derive_fallback_signals([job], query="backend developer")
        self.assertTrue(signals)
        joined = " ".join(signals).lower()
        self.assertTrue(any(term in joined for term in ("python", "api", "backend", "rest")))

    def test_fallback_job_reason_is_specific(self):
        job = self._job()
        reason = derive_fallback_job_reason(job, "data analyst")
        self.assertIn("data analyst", reason.lower())
        self.assertNotIn("through the title and listed responsibilities", reason.lower())

    def test_fallback_summary_uses_themes_not_generic_filler(self):
        jobs = [self._job(), self._job(source_job_id="da-2")]
        signals = derive_fallback_signals(jobs, query="data analyst")
        summary = derive_fallback_summary("data analyst", jobs, signals)
        self.assertIn("data analyst", summary.lower())
        self.assertNotIn("share recurring themes across title", summary.lower())

    def test_parse_llm_json_response(self):
        job = self._job()
        raw = f"""{{
          "summary": "These roles align with your data analyst alert because they emphasize analytical reporting and performance evaluation.",
          "key_signals": [
            "Data analysis and reporting",
            "Business systems analysis",
            "Performance metrics",
            "Position"
          ],
          "job_reasons": {{
            "{job.id}": "This role fits your data analyst alert because it focuses on performance reporting and decision support."
          }}
        }}"""
        parsed = parse_llm_response(raw, jobs=[job])
        self.assertIn("data analyst", parsed.summary.lower())
        self.assertTrue(all(is_quality_signal(s) for s in parsed.key_signals))
        self.assertIn(str(job.id), parsed.job_reasons)
