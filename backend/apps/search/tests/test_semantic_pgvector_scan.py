"""Regression: pgvector must scan past low-quality neighbors (production USAJOBS pattern)."""

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.jobs.models import JobPosting
from apps.search.services.embedding_generation import generate_job_embedding
from apps.search.services.semantic_search import semantic_search_jobs

BACKEND_NL_QUERY = (
    "I enjoy building backend systems, designing APIs, working with databases "
    "and developing scalable applications"
)


@override_settings(
    EMBEDDING_PROVIDER="local",
    EMBEDDING_DIMENSION=384,
    SEMANTIC_TECH_ONLY=False,
    SEMANTIC_SEARCH_CANDIDATE_POOL=20,
    SEMANTIC_SEARCH_SCAN_FLOOR=80,
)
class SemanticPgvectorScanTests(TestCase):
    def setUp(self):
        self.target = JobPosting.objects.create(
            source="adzuna",
            source_job_id="target-backend",
            title="Senior Backend Software Engineer",
            company_name="Tech Co",
            description_clean=(
                "Design and build backend APIs, database schemas, and scalable microservices. "
                "Python, SQL, and cloud deployment experience required for platform services."
            ),
            category_normalized="Software Development",
            job_url="https://example.com/target-backend",
            content_hash="target-backend-hash",
            posted_at=timezone.now(),
        )
        noise_jobs = []
        for idx in range(60):
            noise_jobs.append(
                JobPosting(
                    source="usajobs",
                    source_job_id=f"noise-{idx}",
                    title=f"Program Support Assistant {idx}",
                    company_name="Agency",
                    description_clean="Short posting.",
                    category_normalized="Administrative",
                    job_url=f"https://example.com/noise-{idx}",
                    content_hash=f"noise-hash-{idx}",
                    posted_at=timezone.now(),
                )
            )
        JobPosting.objects.bulk_create(noise_jobs)
        for job in JobPosting.objects.all():
            generate_job_embedding(job)

    def test_nl_query_finds_quality_job_behind_low_quality_neighbors(self):
        results = semantic_search_jobs(BACKEND_NL_QUERY, top_k=5)
        self.assertGreater(
            len(results),
            0,
            "expected quality job after scanning past low-quality pgvector neighbors",
        )
        self.assertEqual(results[0]["job"].id, self.target.id)
