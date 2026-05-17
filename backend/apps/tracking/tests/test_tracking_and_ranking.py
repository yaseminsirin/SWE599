from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.jobs.models import JobPosting
from apps.search.services.embedding_generation import generate_job_embedding
from apps.tracking.models import JobClickEvent, UserSearchEvent

User = get_user_model()


class TrackingAndRankingTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="bob",
            email="bob@example.com",
            password="strong-pass-123",
        )
        self.client.force_authenticate(user=self.user)

        self.job1 = JobPosting.objects.create(
            source="adzuna",
            source_job_id="r1",
            title="Python Backend Engineer",
            normalized_title="python backend engineer",
            company_name="Acme",
            description_clean="Python backend APIs",
            job_url="https://example.com/r1",
            location_text="US",
            city="NY",
            country="US",
            is_remote=True,
            employment_type="full_time",
            content_hash="rank-h1",
            posted_at=timezone.now(),
        )
        self.job2 = JobPosting.objects.create(
            source="remotive",
            source_job_id="r2",
            title="Frontend Developer",
            normalized_title="frontend developer",
            company_name="Beta",
            description_clean="React frontend",
            job_url="https://example.com/r2",
            location_text="DE",
            city="Berlin",
            country="DE",
            is_remote=False,
            employment_type="contract",
            content_hash="rank-h2",
            posted_at=timezone.now(),
        )
        generate_job_embedding(self.job1)
        generate_job_embedding(self.job2)

    def test_tracking_endpoints_create_events(self):
        search_resp = self.client.post(
            reverse("track-search"),
            {"query": "python", "filters": {"is_remote": True}, "result_count": 2},
            format="json",
        )
        self.assertEqual(search_resp.status_code, 201)
        search_event_id = search_resp.data["id"]
        self.assertTrue(UserSearchEvent.objects.filter(id=search_event_id).exists())

        click_resp = self.client.post(
            reverse("track-click"),
            {
                "job_id": self.job1.id,
                "search_event_id": search_event_id,
                "rank_position": 1,
                "keyword_score": 0.8,
                "semantic_score": 0.7,
                "final_score": 0.77,
            },
            format="json",
        )
        self.assertEqual(click_resp.status_code, 201)
        click = JobClickEvent.objects.get(id=click_resp.data["id"])
        self.assertEqual(click.rank_position, 1)

    def test_ranked_search_returns_scoring_fields(self):
        # seed click signal for job1
        JobClickEvent.objects.create(
            user=self.user,
            job=self.job1,
            rank_position=1,
            keyword_score=1.0,
            semantic_score=1.0,
            final_score=1.0,
        )
        resp = self.client.get(reverse("job-ranked-search"), {"top_k": 10})
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data["count"], 2)
        first = resp.data["results"][0]
        self.assertIn("rank_position", first)
        self.assertIn("keyword_score", first)
        self.assertIn("semantic_score", first)
        self.assertIn("click_score", first)
        self.assertIn("final_score", first)
