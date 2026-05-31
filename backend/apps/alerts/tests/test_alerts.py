from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.alerts.models import AlertDeliveryLog, JobAlert
from apps.alerts.services.matching import process_job_alerts
from apps.jobs.models import JobPosting

_TECH_DESC = (
    "Python backend developer building REST APIs, Django services, and cloud deployments. "
    "Requires Python, SQL, and distributed systems experience."
)


def _make_job(**overrides) -> JobPosting:
    defaults = {
        "source": "adzuna",
        "source_job_id": "alert-1",
        "title": "Python Backend Engineer",
        "normalized_title": "python backend engineer",
        "company_name": "Acme",
        "description_clean": _TECH_DESC,
        "job_url": "https://example.com/1",
        "location_text": "US",
        "city": "NY",
        "country": "US",
        "is_remote": True,
        "employment_type": "full_time",
        "content_hash": "alert-h1",
        "posted_at": timezone.now(),
        "normalized_at": timezone.now(),
    }
    defaults.update(overrides)
    return JobPosting.objects.create(**defaults)


class AlertsTests(APITestCase):
    def setUp(self):
        JobAlert.objects.all().delete()

    def test_alert_crud_without_login(self):
        create = self.client.post(
            reverse("alert-list-create"),
            {
                "name": "Python Alerts",
                "keyword": "python",
                "location_text": "US",
                "is_remote": True,
                "employment_type": "full_time",
                "filters": {"search_mode": "semantic", "seniority": "senior"},
                "notify_email": "alerts@example.com",
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        self.assertEqual(create.data["filters"]["search_mode"], "semantic")
        alert_id = create.data["id"]

        list_resp = self.client.get(reverse("alert-list-create"))
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(list_resp.data["count"], 1)

        patch_resp = self.client.patch(
            reverse("alert-detail", kwargs={"pk": alert_id}),
            {"keyword": "django"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.data["keyword"], "django")

        delete_resp = self.client.delete(reverse("alert-detail", kwargs={"pk": alert_id}))
        self.assertEqual(delete_resp.status_code, 204)

    def test_alert_requires_email(self):
        resp = self.client.post(
            reverse("alert-list-create"),
            {"keyword": "python"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("notify_email", resp.data)

    @patch("apps.alerts.services.matching.send_transactional_email")
    @patch("apps.alerts.services.rag.email_generation.get_llm_provider", return_value=None)
    @patch("apps.alerts.services.matching.retrieve_alert_jobs")
    def test_alert_processing_matches_and_prevents_duplicate_delivery(
        self, mock_retrieve, _mock_llm, mock_brevo
    ):
        mock_brevo.return_value = {"messageId": "test-id"}
        alert = JobAlert.objects.create(
            keyword="python",
            is_active=True,
            notify_email="alerts@example.com",
        )
        job = _make_job()
        mock_retrieve.return_value = [job]

        first = process_job_alerts(max_results_per_alert=20)
        self.assertEqual(first["alerts_notified"], 1)
        self.assertEqual(AlertDeliveryLog.objects.count(), 1)

        mock_retrieve.return_value = [job]
        second = process_job_alerts(max_results_per_alert=20)
        self.assertEqual(second["alerts_notified"], 0)
        self.assertEqual(AlertDeliveryLog.objects.count(), 1)
        alert.refresh_from_db()
        self.assertIsNotNone(alert.last_notified_at)
