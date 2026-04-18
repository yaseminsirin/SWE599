from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.alerts.models import AlertDeliveryLog, JobAlert
from apps.alerts.services.matching import process_job_alerts
from apps.jobs.models import JobPosting

User = get_user_model()


class AlertsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="strong-pass-123",
        )
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_alert_crud_with_authenticated_ownership(self):
        create = self.client.post(
            reverse("alert-list-create"),
            {
                "name": "Python Alerts",
                "keyword": "python",
                "location_text": "US",
                "is_remote": True,
                "employment_type": "full_time",
                "filters": {"seniority": "senior"},
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
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

    def test_alert_processing_matches_and_prevents_duplicate_delivery(self):
        alert = JobAlert.objects.create(
            user=self.user,
            keyword="python",
            is_active=True,
        )
        JobPosting.objects.create(
            source="adzuna",
            source_job_id="1",
            title="Python Backend Engineer",
            normalized_title="python backend engineer",
            company_name="Acme",
            description_clean="Python APIs",
            job_url="https://example.com/1",
            location_text="US",
            city="NY",
            country="US",
            is_remote=True,
            employment_type="full_time",
            content_hash="alert-h1",
            posted_at=timezone.now(),
            normalized_at=timezone.now(),
        )

        first = process_job_alerts(max_results_per_alert=20)
        self.assertEqual(first["alerts_notified"], 1)
        self.assertEqual(AlertDeliveryLog.objects.count(), 1)

        second = process_job_alerts(max_results_per_alert=20)
        self.assertEqual(second["delivery_duplicates"], 0)
        self.assertEqual(AlertDeliveryLog.objects.count(), 1)
        alert.refresh_from_db()
        self.assertIsNotNone(alert.last_notified_at)
