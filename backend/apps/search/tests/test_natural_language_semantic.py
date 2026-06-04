"""Natural-language semantic search regression tests."""

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.jobs.models import JobPosting
from apps.search.services.embedding_generation import generate_job_embedding
from apps.search.services.retrieval_rerank import (
    extract_skill_terms,
    is_natural_language_query,
    is_relevant_semantic_match,
    retrieval_query_text,
    should_skip_pgvector_prefilter,
)
from apps.search.services.semantic_search import semantic_search_jobs

BACKEND_NL_QUERY = (
    "I enjoy building backend systems, designing APIs, working with databases "
    "and developing scalable applications"
)

ANALYST_NL_QUERY = (
    "I have experience analyzing data, creating dashboards and generating business insights"
)


@override_settings(
    EMBEDDING_PROVIDER="local",
    EMBEDDING_DIMENSION=384,
    SEMANTIC_TECH_ONLY=False,
)
class NaturalLanguageSemanticSearchTests(TestCase):
    def setUp(self):
        self.backend_job = JobPosting.objects.create(
            source="remotive",
            source_job_id="be-1",
            title="Senior Backend Software Engineer",
            company_name="Tech Co",
            description_clean=(
                "Design and build backend APIs, database schemas, and scalable microservices. "
                "Python, SQL, and cloud deployment experience required."
            ),
            category_normalized="Software Development",
            job_url="https://example.com/be-1",
            content_hash="be-hash-1",
            posted_at=timezone.now(),
        )
        self.analyst_job = JobPosting.objects.create(
            source="adzuna",
            source_job_id="da-1",
            title="Business Data Analyst",
            company_name="Analytics Inc",
            description_clean=(
                "Analyze business data, build dashboards and reporting for stakeholders. "
                "Generate insights from SQL databases and BI tools."
            ),
            category_normalized="Data Science and Analytics",
            job_url="https://example.com/da-1",
            content_hash="da-hash-1",
            posted_at=timezone.now(),
        )
        self.unrelated_job = JobPosting.objects.create(
            source="usajobs",
            source_job_id="truck-1",
            title="CDL Truck Driver",
            company_name="Logistics LLC",
            description_clean=(
                "Commercial truck driver for long haul routes. CDL license required. "
                "No software development responsibilities."
            ),
            category_normalized="Transportation",
            job_url="https://example.com/truck-1",
            content_hash="truck-hash-1",
            posted_at=timezone.now(),
        )
        for job in (self.backend_job, self.analyst_job, self.unrelated_job):
            generate_job_embedding(job)

    def test_detects_natural_language_queries(self):
        self.assertTrue(is_natural_language_query(BACKEND_NL_QUERY))
        self.assertTrue(is_natural_language_query(ANALYST_NL_QUERY))
        self.assertFalse(is_natural_language_query("python developer"))

    def test_skips_pgvector_prefilter_for_nl(self):
        self.assertTrue(should_skip_pgvector_prefilter(BACKEND_NL_QUERY))

    def test_retrieval_text_for_backend_nl_query(self):
        compact = retrieval_query_text(BACKEND_NL_QUERY)
        self.assertIn("backend", compact)
        self.assertIn("developer", compact)
        self.assertIn("api", compact)
        self.assertIn("database", compact)
        skills = extract_skill_terms(BACKEND_NL_QUERY)
        self.assertIn("backend", skills)
        self.assertIn("developer", skills)

    def test_retrieval_text_for_analyst_nl_query(self):
        compact = retrieval_query_text(ANALYST_NL_QUERY)
        self.assertIn("data", compact)
        self.assertIn("dashboard", compact)
        self.assertIn("insights", compact)

    def test_single_term_backend_allows_body_match(self):
        job = JobPosting.objects.create(
            source="remotive",
            source_job_id="be-body-1",
            title="Python Developer",
            company_name="Co",
            description_clean="Work on server-side backend services and REST endpoints.",
            job_url="https://example.com/be-body",
            content_hash="be-body-hash",
            posted_at=timezone.now(),
        )
        self.assertTrue(
            is_relevant_semantic_match(
                "backend",
                job,
                hybrid_score=0.3,
                lexical_score=0.05,
                semantic_score=0.25,
            )
        )

    def test_backend_nl_query_returns_software_roles(self):
        results = semantic_search_jobs(BACKEND_NL_QUERY, top_k=5)
        self.assertGreater(len(results), 0, "NL backend query should not return zero results")
        titles = " ".join(row["job"].title.lower() for row in results)
        self.assertTrue(
            any(
                token in titles
                for token in ("backend", "software", "engineer", "developer", "api", "data engineer")
            ),
            f"Unexpected titles: {titles}",
        )
        result_ids = {row["job"].id for row in results}
        self.assertNotIn(self.unrelated_job.id, result_ids)

    def test_analyst_nl_query_returns_analytics_roles(self):
        results = semantic_search_jobs(ANALYST_NL_QUERY, top_k=5)
        self.assertGreater(len(results), 0, "NL analyst query should not return zero results")
        top_id = results[0]["job"].id
        self.assertEqual(top_id, self.analyst_job.id)
        result_ids = {row["job"].id for row in results}
        self.assertNotIn(self.unrelated_job.id, result_ids)
