from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.jobs.models import JobPosting
from apps.jobs.services.demo_dataset import DEMO_SOURCE
from apps.search.services.job_quality import apply_keyword_token_filter, is_quality_job, is_tech_related_job
from apps.search.services.retrieval_rerank import (
    compute_hybrid_score,
    compute_lexical_score,
    filter_relevant_semantic_results,
    is_relevant_semantic_match,
    rerank_semantic_candidates,
    retrieval_query_text,
)
from apps.search.services.semantic_search import semantic_search_jobs
from django.utils import timezone


class RealDataRetrievalTests(TestCase):
    def setUp(self):
        self.real_job = JobPosting.objects.create(
            source="adzuna",
            source_job_id="real-1",
            title="Python Backend Developer",
            normalized_title="python backend developer",
            company_name="Acme",
            description_clean=(
                "Build Python APIs and Django services for a SaaS platform. "
                "Write tests, review pull requests, and deploy backend features."
            ),
            job_url="https://example.com/jobs/1",
            content_hash="real-hash-1",
            posted_at=timezone.now(),
        )
        JobPosting.objects.create(
            source=DEMO_SOURCE,
            source_job_id="demo-1",
            title="Python Backend Developer",
            company_name="Demo Co",
            description_clean=(
                "Demo only job posting for local testing. Not used in final presentation workflow."
            ),
            job_url="https://demo.jobsense.example/jobs/demo-1",
            content_hash="demo-hash-1",
            posted_at=timezone.now(),
        )

    def test_keyword_token_filter_matches_any_token(self):
        qs = JobPosting.objects.exclude(source=DEMO_SOURCE)
        matched = apply_keyword_token_filter(qs, "python backend developer")
        self.assertEqual(matched.count(), 1)
        self.assertEqual(matched.first().source, "adzuna")

    def test_quality_and_tech_heuristics(self):
        self.assertTrue(is_quality_job(self.real_job))
        self.assertTrue(is_tech_related_job(self.real_job))

    def test_hybrid_rerank_prefers_title_overlap(self):
        other = JobPosting.objects.create(
            source="usajobs",
            source_job_id="real-2",
            title="Transportation Security Officer",
            company_name="Gov",
            description_clean="Federal security role unrelated to software development.",
            job_url="https://example.com/jobs/2",
            content_hash="real-hash-2",
            posted_at=timezone.now(),
        )
        candidates = [
            {"job": other, "semantic_score": 0.9},
            {"job": self.real_job, "semantic_score": 0.7},
        ]
        reranked = rerank_semantic_candidates("python backend developer", candidates)
        self.assertEqual(reranked[0]["job"].id, self.real_job.id)
        self.assertGreater(reranked[0]["hybrid_score"], reranked[1]["hybrid_score"])

    def test_irrelevant_truck_driver_filtered_for_python_query(self):
        truck_job = JobPosting.objects.create(
            source="adzuna",
            source_job_id="truck-1",
            title="Regional Truck Driver Owner Operator",
            company_name="UACL Logistics",
            description_clean=(
                "Seeking Class A CDL Van and Flatbed Owner Operators. "
                "Sign-on bonus available for qualified drivers with six months experience."
            ),
            category_normalized="Logistics & Warehouse Jobs",
            job_url="https://example.com/truck-1",
            content_hash="truck-hash-1",
            posted_at=timezone.now(),
        )
        candidates = [
            {"job": truck_job, "semantic_score": 0.82, "lexical_score": 0.0, "hybrid_score": 0.57},
            {
                "job": self.real_job,
                "semantic_score": 0.74,
                "lexical_score": compute_lexical_score("python backend developer", self.real_job),
                "hybrid_score": compute_hybrid_score(
                    semantic_score=0.74,
                    lexical_score=compute_lexical_score("python backend developer", self.real_job),
                ),
            },
        ]
        filtered = filter_relevant_semantic_results(
            "Python developer with backend experience building REST APIs and web services",
            candidates,
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["job"].id, self.real_job.id)
        self.assertFalse(
            is_relevant_semantic_match(
                "python developer",
                truck_job,
                hybrid_score=0.57,
                lexical_score=0.0,
                semantic_score=0.82,
            )
        )

    def test_long_natural_language_query_keeps_python_job(self):
        long_query = (
            "Python developer with backend experience building REST APIs, "
            "web services, and data-driven applications"
        )
        candidates = [
            {
                "job": self.real_job,
                "semantic_score": 0.71,
                "lexical_score": compute_lexical_score(long_query, self.real_job),
                "hybrid_score": compute_hybrid_score(
                    semantic_score=0.71,
                    lexical_score=compute_lexical_score(long_query, self.real_job),
                ),
            },
        ]
        filtered = filter_relevant_semantic_results(long_query, candidates)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["job"].id, self.real_job.id)

    def test_retrieval_query_text_shortens_long_natural_language(self):
        long_query = (
            "Python developer with backend experience building REST APIs, "
            "web services, and data-driven applications"
        )
        compact = retrieval_query_text(long_query)
        self.assertIn("python", compact)
        self.assertIn("developer", compact)
        self.assertLess(len(compact.split()), len(long_query.split()))
        self.assertEqual(retrieval_query_text("python developer"), "developer python")

    def test_query_term_prefilter_narrows_pgvector_scope(self):
        from apps.search.services.job_quality import narrow_jobs_by_terms
        from apps.search.services.semantic_search import _query_prefilter_terms

        truck_job = JobPosting.objects.create(
            source="adzuna",
            source_job_id="truck-2",
            title="Regional Truck Driver Owner Operator",
            company_name="UACL Logistics",
            description_clean=(
                "Seeking Class A CDL Van and Flatbed Owner Operators with experience "
                "operating commercial routes across regional lanes."
            ),
            category_normalized="Logistics & Warehouse Jobs",
            job_url="https://example.com/truck-2",
            content_hash="truck-hash-2",
            posted_at=timezone.now(),
        )
        long_query = (
            "Python developer with backend experience building REST APIs, "
            "web services, and data-driven applications"
        )
        terms = _query_prefilter_terms(long_query)
        qs = narrow_jobs_by_terms(JobPosting.objects.all(), terms)
        ids = set(qs.values_list("id", flat=True))
        self.assertIn(self.real_job.id, ids)
        self.assertNotIn(truck_job.id, ids)

    @override_settings(SEMANTIC_TECH_ONLY=True)
    @patch("apps.search.services.semantic_search.embed_text")
    @patch("apps.search.services.semantic_search.JobEmbedding")
    def test_semantic_search_excludes_demo_source(self, mock_embedding_model, mock_embed):
        mock_embed.return_value = [0.0] * 768
        row = MagicMock()
        row.job = self.real_job
        row.distance = 0.2
        mock_embedding_model.objects.filter.return_value.annotate.return_value.select_related.return_value.order_by.return_value = [
            row
        ]

        results = semantic_search_jobs("python backend", top_k=5, tech_only=False)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["job"].source, "adzuna")
        self.assertTrue(mock_embedding_model.objects.filter.called)
        call_kwargs = mock_embedding_model.objects.filter.call_args[1]
        self.assertIn("job_id__in", call_kwargs)
