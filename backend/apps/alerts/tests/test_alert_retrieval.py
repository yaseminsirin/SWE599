from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.alerts.models import AlertDeliveryLog, JobAlert
from apps.alerts.services.alert_retrieval import retrieve_alert_jobs
from apps.jobs.models import JobPosting

_TECH_DESC = (
    "Python backend developer building REST APIs, Django services, and cloud deployments. "
    "Requires Python, SQL, and distributed systems experience."
)


def _make_job(**overrides) -> JobPosting:
    defaults = {
        "source": "adzuna",
        "source_job_id": "retrieval-1",
        "title": "Python Backend Engineer",
        "normalized_title": "python backend engineer",
        "company_name": "Acme",
        "description_clean": _TECH_DESC,
        "job_url": "https://example.com/jobs/1",
        "location_text": "US",
        "city": "NY",
        "country": "US",
        "is_remote": True,
        "employment_type": "full_time",
        "content_hash": "retrieval-h1",
        "posted_at": timezone.now(),
        "normalized_at": timezone.now(),
    }
    defaults.update(overrides)
    return JobPosting.objects.create(**defaults)


class AlertRetrievalTests(TestCase):
    def setUp(self):
        self.alert = JobAlert.objects.create(
            keyword="python backend",
            is_active=True,
            notify_email="alerts@example.com",
        )
        self.job = _make_job()

    def test_retrieve_limits_to_max_twenty(self):
        jobs = [_make_job(source_job_id=f"j-{i}", content_hash=f"h-{i}") for i in range(25)]
        with patch(
            "apps.alerts.services.alert_retrieval._semantic_ranked_jobs",
            return_value=jobs,
        ):
            selected = retrieve_alert_jobs(self.alert, min_results=10, max_results=20)
        self.assertLessEqual(len(selected), 20)

    def test_skips_previously_delivered_jobs(self):
        AlertDeliveryLog.objects.create(alert=self.alert, job=self.job)
        with patch(
            "apps.alerts.services.alert_retrieval._semantic_ranked_jobs",
            return_value=[self.job],
        ):
            selected = retrieve_alert_jobs(self.alert, max_results=20)
        self.assertEqual(selected, [])

    def test_prefers_jobs_new_since_last_notified(self):
        older = _make_job(source_job_id="old", content_hash="old-h")
        newer = _make_job(source_job_id="new", content_hash="new-h")
        self.alert.last_notified_at = timezone.now() - timezone.timedelta(days=1)
        self.alert.save(update_fields=["last_notified_at"])
        older.normalized_at = timezone.now() - timezone.timedelta(days=2)
        older.save(update_fields=["normalized_at"])
        newer.normalized_at = timezone.now()
        newer.save(update_fields=["normalized_at"])

        with patch(
            "apps.alerts.services.alert_retrieval._semantic_ranked_jobs",
            return_value=[older, newer],
        ):
            selected = retrieve_alert_jobs(self.alert, min_results=1, max_results=20)
        self.assertEqual([j.id for j in selected], [newer.id])
