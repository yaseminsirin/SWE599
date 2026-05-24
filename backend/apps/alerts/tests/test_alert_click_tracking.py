from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.jobs.models import JobPosting
from apps.tracking.models import JobClickEvent

_TECH_DESC = (
    "Python backend developer building REST APIs, Django services, and cloud deployments. "
    "Requires Python, SQL, and distributed systems experience."
)


class AlertClickTrackingTests(TestCase):
    def setUp(self):
        self.job = JobPosting.objects.create(
            source="adzuna",
            source_job_id="click-1",
            title="Python Backend Engineer",
            company_name="Acme",
            description_clean=_TECH_DESC,
            job_url="https://example.com/click-1",
            content_hash="click-h1",
            posted_at=timezone.now(),
            normalized_at=timezone.now(),
        )

    @override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
    def test_alert_click_redirect_records_event_and_redirects(self):
        url = reverse("track-alert-click", kwargs={"job_id": self.job.id})
        response = self.client.get(url + "?alert_id=1")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://example.com/click-1")
        self.assertEqual(JobClickEvent.objects.filter(job=self.job).count(), 1)
