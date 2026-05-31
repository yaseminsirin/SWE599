from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.jobs.models import JobPosting
from apps.search.models import JobEmbedding
from apps.search.services.embedding_generation import (
    generate_job_embedding,
    regenerate_job_embeddings,
)
from apps.search.services.semantic_search import semantic_search_jobs
from apps.search.services.vector_query import distance_to_similarity


@override_settings(
    EMBEDDING_PROVIDER="local",
    EMBEDDING_DIMENSION=384,
    SEMANTIC_TECH_ONLY=False,
)
class PgvectorTests(TestCase):
    def setUp(self):
        self.job_python = JobPosting.objects.create(
            source="adzuna",
            employment_type="full_time",
            source_job_id="pv-1",
            title="Python Backend Engineer",
            normalized_title="python backend engineer",
            company_name="Acme",
            description_clean=(
                "Build backend APIs with Python and Django. Design REST services, "
                "write automated tests, and deploy scalable software to production."
            ),
            job_url="https://example.com/pv-1",
            location_text="New York, US",
            content_hash="pv-h1",
            posted_at=timezone.now(),
        )
        self.job_sales = JobPosting.objects.create(
            source="adzuna",
            source_job_id="pv-2",
            title="Sales Representative",
            normalized_title="sales representative",
            company_name="Beta",
            description_clean=(
                "B2B sales and client acquisition for enterprise accounts. "
                "Manage pipelines, forecasts, and quarterly revenue targets."
            ),
            job_url="https://example.com/pv-2",
            location_text="Chicago, US",
            content_hash="pv-h2",
            posted_at=timezone.now(),
        )

    def test_pgvector_extension_enabled(self):
        self.assertEqual(connection.vendor, "postgresql")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            self.assertIsNotNone(cursor.fetchone())

    def test_embedding_stored_as_vector_field(self):
        row = generate_job_embedding(self.job_python)
        from django.conf import settings

        self.assertEqual(row.vector_dimension, settings.EMBEDDING_DIMENSION)
        self.assertEqual(len(list(row.embedding)), settings.EMBEDDING_DIMENSION)
        field = JobEmbedding._meta.get_field("embedding")
        self.assertEqual(field.__class__.__name__, "VectorField")

    def test_semantic_search_orders_by_pgvector_similarity(self):
        generate_job_embedding(self.job_python)
        generate_job_embedding(self.job_sales)
        results = semantic_search_jobs("python django backend", top_k=5)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["job"].id, self.job_python.id)
        self.assertGreater(results[0]["semantic_score"], 0.0)
        result_ids = {row["job"].id for row in results}
        self.assertNotIn(self.job_sales.id, result_ids)

    def test_distance_to_similarity_clamped(self):
        self.assertAlmostEqual(distance_to_similarity(0.0), 1.0)
        self.assertAlmostEqual(distance_to_similarity(1.0), 0.0)

    def test_regenerate_embeddings_rebuilds_rows(self):
        generate_job_embedding(self.job_python)
        summary = regenerate_job_embeddings(
            tech_only=False,
            missing_only=False,
            force=True,
            sleep_seconds=0,
        )
        self.assertGreaterEqual(summary["regenerated"], 2)
        self.assertTrue(
            JobEmbedding.objects.filter(job=self.job_python).exists()
        )

    def test_semantic_api_still_returns_scores(self):
        generate_job_embedding(self.job_python)
        generate_job_embedding(self.job_sales)
        resp = self.client.get(
            reverse("job-semantic-search"),
            {"q": "python backend", "top_k": 10},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("semantic_score", resp.data["results"][0])
