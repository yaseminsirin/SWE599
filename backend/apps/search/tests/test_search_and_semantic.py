from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.jobs.models import JobPosting
from apps.search.models import JobEmbedding
from apps.search.services.embedding_generation import generate_job_embedding
from apps.search.services.similarity import cosine_similarity


class SearchAndSemanticTests(APITestCase):
    def setUp(self):
        self.job1 = JobPosting.objects.create(
            source="adzuna",
            source_job_id="1",
            title="Python Backend Engineer",
            normalized_title="python backend engineer",
            company_name="Acme",
            description_clean="Build backend APIs with Python",
            job_url="https://example.com/1",
            location_text="New York, US",
            city="New York",
            country="US",
            is_remote=True,
            employment_type="full_time",
            content_hash="h1",
            posted_at=timezone.now(),
        )
        self.job2 = JobPosting.objects.create(
            source="remotive",
            source_job_id="2",
            title="Data Analyst",
            normalized_title="data analyst",
            company_name="Beta",
            description_clean="Analyze datasets and build dashboards",
            job_url="https://example.com/2",
            location_text="Berlin, DE",
            city="Berlin",
            country="DE",
            is_remote=False,
            employment_type="contract",
            content_hash="h2",
            posted_at=timezone.now(),
        )

    def test_search_filters_and_pagination(self):
        resp = self.client.get(
            reverse("job-search"),
            {
                "keyword": "python",
                "location": "new york",
                "is_remote": "true",
                "employment_type": "full_time",
                "page": 1,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("count", resp.data)
        self.assertIn("results", resp.data)
        self.assertIn("next", resp.data)
        self.assertIn("previous", resp.data)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], self.job1.id)

    def test_embedding_generation_stores_embedding(self):
        generate_job_embedding(self.job1)
        row = JobEmbedding.objects.get(job=self.job1)
        self.assertEqual(row.provider, "local")
        self.assertGreater(row.vector_dimension, 0)
        self.assertEqual(len(row.embedding), row.vector_dimension)

    def test_semantic_endpoint_returns_ranked_results(self):
        generate_job_embedding(self.job1)
        generate_job_embedding(self.job2)
        resp = self.client.get(reverse("job-semantic-search"), {"q": "python backend", "top_k": 10})
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data["count"], 2)
        self.assertIn("semantic_score", resp.data["results"][0])

    def test_cosine_similarity_utility(self):
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)
