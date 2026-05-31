from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.jobs.models import JobPosting
from apps.jobs.services.job_urls import resolve_external_job_url
from apps.tracking.models import JobClickEvent

_TECH_DESC = (
    "Python backend developer building REST APIs, Django services, and cloud deployments. "
    "Requires Python, SQL, and distributed systems experience."
)


class ResolveExternalJobUrlTests(TestCase):
    def test_accepts_real_http_urls(self):
        self.assertEqual(
            resolve_external_job_url("https://www.adzuna.com/details/123"),
            "https://www.adzuna.com/details/123",
        )

    def test_rejects_demo_and_invalid_hosts(self):
        self.assertIsNone(resolve_external_job_url("https://demo.jobsense.example/jobs/slug"))
        self.assertIsNone(resolve_external_job_url("https://example.invalid/jobs/adzuna/1"))
        self.assertIsNone(resolve_external_job_url("ftp://example.com/job"))
        self.assertIsNone(resolve_external_job_url(""))
        self.assertIsNone(resolve_external_job_url("   "))


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

    @override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SITE_URL="http://testserver")
    def test_alert_click_redirect_records_event_and_opens_listing(self):
        url = reverse("track-alert-click", kwargs={"job_id": self.job.id})
        response = self.client.get(url + "?alert_id=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("https://example.com/click-1", response.content.decode())
        self.assertEqual(JobClickEvent.objects.filter(job=self.job).count(), 1)

    @override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SITE_URL="http://testserver")
    def test_alert_click_with_invalid_job_url_shows_search_fallback(self):
        self.job.job_url = "https://demo.jobsense.example/jobs/demo"
        self.job.save(update_fields=["job_url"])
        url = reverse("track-alert-click", kwargs={"job_id": self.job.id})
        response = self.client.get(url + "?alert_id=1")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("no longer available", content)
        self.assertIn("http://testserver/search/", content)
        self.assertEqual(JobClickEvent.objects.filter(job=self.job).count(), 1)
