"""Quality regression tests for semantic search (run before shipping ranking changes)."""

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.jobs.models import JobPosting
from apps.search.services.embedding_generation import generate_job_embedding
from apps.search.services.job_quality import narrow_jobs_by_terms
from apps.search.services.retrieval_rerank import (
    compute_hybrid_score,
    compute_lexical_score,
    filter_relevant_semantic_results,
    prefilter_terms,
    retrieval_query_text,
)
from apps.search.services.semantic_search import semantic_search_jobs

_LONG_QUERY = (
    "Python developer with backend experience building REST APIs, "
    "web services, and data-driven applications"
)
_SHORT_QUERY = "python developer"

_TECH_DESC = (
    "Python backend developer building REST APIs, Django services, and cloud deployments. "
    "Requires Python, SQL, and distributed systems experience."
)


@override_settings(
    EMBEDDING_PROVIDER="local",
    EMBEDDING_DIMENSION=384,
    SEMANTIC_TECH_ONLY=False,
)
class SemanticSearchQualityTests(TestCase):
    def setUp(self):
        self.python_job = JobPosting.objects.create(
            source="usajobs",
            source_job_id="py-1",
            title="Python Developer",
            normalized_title="python developer",
            company_name="Social Security Administration",
            description_clean=_TECH_DESC,
            category_normalized="Information Technology Management",
            job_url="https://example.com/py-1",
            content_hash="py-hash-1",
            posted_at=timezone.now(),
        )
        self.clerk_job = JobPosting.objects.create(
            source="usajobs",
            source_job_id="clerk-1",
            title="Program Support Assistant (OA) - Work Order Technician",
            company_name="Veterans Health Administration",
            description_clean=(
                "Administrative and technical support for Engineering Service. "
                "Enter data into spreadsheets, coordinate work orders, and assist customers."
            ),
            category_normalized="Miscellaneous Clerk And Assistant",
            job_url="https://example.com/clerk-1",
            content_hash="clerk-hash-1",
            posted_at=timezone.now(),
        )
        self.psych_job = JobPosting.objects.create(
            source="adzuna",
            source_job_id="psych-1",
            title="Locums Psychiatrist",
            company_name="Weatherby Healthcare",
            description_clean=(
                "Healthcare provider seeking psychiatrist for outpatient clinic. "
                "Treat children and adults; part-time schedule available."
            ),
            category_normalized="Healthcare & Nursing Jobs",
            job_url="https://example.com/psych-1",
            content_hash="psych-hash-1",
            posted_at=timezone.now(),
        )
        for job in (self.python_job, self.clerk_job, self.psych_job):
            generate_job_embedding(job)

    def test_prefilter_uses_strong_terms_not_generic_data_or_web(self):
        terms = prefilter_terms(_LONG_QUERY)
        self.assertIn("python", terms)
        self.assertIn("developer", terms)
        self.assertNotIn("data", terms)
        self.assertNotIn("web", terms)
        compact = retrieval_query_text(_LONG_QUERY)
        self.assertNotIn("data", compact.split())
        self.assertNotIn("web", compact.split())

    def test_dev_short_query_expands_to_developer_terms(self):
        terms = prefilter_terms("dev")
        self.assertIn("developer", terms)
        self.assertIn("engineer", terms)
        compact = retrieval_query_text("dev")
        self.assertIn("developer", compact)

    def test_prefilter_excludes_clerk_and_psychiatrist(self):
        terms = prefilter_terms(_LONG_QUERY)
        matched_ids = set(narrow_jobs_by_terms(JobPosting.objects.all(), terms).values_list("id", flat=True))
        self.assertIn(self.python_job.id, matched_ids)
        self.assertNotIn(self.clerk_job.id, matched_ids)
        self.assertNotIn(self.psych_job.id, matched_ids)

    def test_relevance_filter_drops_clerk_and_psychiatrist(self):
        candidates = []
        for job, semantic in (
            (self.clerk_job, 0.78),
            (self.psych_job, 0.76),
            (self.python_job, 0.72),
        ):
            lexical = compute_lexical_score(_LONG_QUERY, job)
            candidates.append(
                {
                    "job": job,
                    "semantic_score": semantic,
                    "lexical_score": lexical,
                    "hybrid_score": compute_hybrid_score(
                        semantic_score=semantic,
                        lexical_score=lexical,
                    ),
                }
            )
        filtered = filter_relevant_semantic_results(_LONG_QUERY, candidates)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["job"].id, self.python_job.id)

    def test_long_and_short_queries_return_same_top_job(self):
        short_results = semantic_search_jobs(_SHORT_QUERY, top_k=5)
        long_results = semantic_search_jobs(_LONG_QUERY, top_k=5)
        self.assertGreaterEqual(len(short_results), 1)
        self.assertGreaterEqual(len(long_results), 1)
        self.assertEqual(short_results[0]["job"].id, self.python_job.id)
        self.assertEqual(long_results[0]["job"].id, self.python_job.id)
        result_ids = {row["job"].id for row in long_results}
        self.assertNotIn(self.clerk_job.id, result_ids)
        self.assertNotIn(self.psych_job.id, result_ids)

    def test_dev_query_returns_python_developer(self):
        results = semantic_search_jobs("dev", top_k=5)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["job"].id, self.python_job.id)

    def test_semantic_api_long_query_returns_python_job(self):
        response = self.client.get(
            reverse("job-semantic-search"),
            {"q": _LONG_QUERY, "top_k": 10},
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.data["count"], 0)
        titles = [row["title"].lower() for row in response.data["results"]]
        self.assertTrue(any("python" in title for title in titles))
        self.assertFalse(any("psychiatrist" in title for title in titles))
        self.assertFalse(any("program support assistant" in title for title in titles))
