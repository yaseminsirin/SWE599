from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.jobs.models import JobPosting
from apps.jobs.services.demo_dataset import DEMO_SOURCE
from apps.search.services.job_quality import apply_keyword_token_filter, is_quality_job, is_tech_related_job
from apps.search.services.retrieval_rerank import (
    apply_relevance_with_fallback,
    compute_hybrid_score,
    compute_lexical_score,
    compute_role_alignment_score,
    filter_relevant_semantic_results,
    is_domain_mismatch,
    is_misleading_engineer_listing,
    is_relevant_semantic_match,
    prefilter_terms,
    rerank_semantic_candidates,
    retrieval_query_text,
    specific_query_terms,
)
from apps.search.services.job_quality import narrow_jobs_by_terms, narrow_jobs_for_semantic_search
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

    def test_backend_engineer_specific_term_excludes_staff_product_engineer(self):
        staff_product = JobPosting.objects.create(
            source="remotive",
            source_job_id="staff-product-1",
            title="Staff Product Engineer",
            normalized_title="staff product engineer",
            company_name="LawnStarter",
            description_clean=(
                "Lead product engineering initiatives across cross-functional teams. "
                "Define roadmap, run discovery, and ship customer-facing features."
            ),
            category_normalized="Product Management",
            job_url="https://example.com/staff-product",
            content_hash="staff-product-hash",
            posted_at=timezone.now(),
        )
        backend_job = JobPosting.objects.create(
            source="remotive",
            source_job_id="backend-eng-1",
            title="Backend Engineer",
            normalized_title="backend engineer",
            company_name="Tech Co",
            description_clean=(
                "Build backend APIs, database schemas, and scalable services with Python. "
                "Design REST endpoints and deploy cloud-native applications."
            ),
            category_normalized="Software Development",
            job_url="https://example.com/backend-eng",
            content_hash="backend-eng-hash",
            posted_at=timezone.now(),
        )
        query = "backend engineer"
        self.assertEqual(specific_query_terms(prefilter_terms(query)), {"backend"})
        self.assertFalse(
            is_relevant_semantic_match(
                query,
                staff_product,
                hybrid_score=0.55,
                lexical_score=compute_lexical_score(query, staff_product),
                semantic_score=0.62,
            )
        )
        candidates = [
            {"job": staff_product, "semantic_score": 0.62},
            {"job": backend_job, "semantic_score": 0.58},
        ]
        reranked = rerank_semantic_candidates(query, candidates)
        self.assertEqual(reranked[0]["job"].id, backend_job.id)
        filtered = filter_relevant_semantic_results(query, reranked)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["job"].id, backend_job.id)

    def test_backend_engineer_rejects_non_tech_physicist_false_positive(self):
        physicist = JobPosting.objects.create(
            source="usajobs",
            source_job_id="nasa-physicist",
            title="Physicist, AST, Electronics of Materials (Direct Hire)",
            company_name="George C. Marshall Space Flight Center",
            description_clean=(
                "Support mission critical avionics by selecting and qualifying EEE parts. "
                "Work with backend avionics subsystems and engineering reliability requirements."
            ),
            category_normalized="Physics",
            job_url="https://example.com/nasa-physicist",
            content_hash="nasa-physicist-hash",
            posted_at=timezone.now(),
        )
        query = "backend engineer"
        self.assertTrue(is_domain_mismatch(query, physicist))
        self.assertFalse(
            is_relevant_semantic_match(
                query,
                physicist,
                hybrid_score=0.5,
                lexical_score=compute_lexical_score(query, physicist),
                semantic_score=0.55,
            )
        )
        reranked = rerank_semantic_candidates(
            query,
            [{"job": physicist, "semantic_score": 0.55}],
        )
        relevant, _used_fallback = apply_relevance_with_fallback(query, reranked)
        self.assertEqual(relevant, [])

    def test_backend_engineer_accepts_software_engineer_without_backend_in_title(self):
        software_engineer = JobPosting.objects.create(
            source="usajobs",
            source_job_id="sw-eng-usa",
            title="Computer Engineer (Cybersecurity)",
            company_name="Agency",
            description_clean=(
                "Design and maintain secure software systems, APIs, and backend services "
                "for mission applications. Python and cloud experience preferred."
            ),
            category_normalized="Information Technology",
            job_url="https://example.com/sw-eng-usa",
            content_hash="sw-eng-usa-hash",
            posted_at=timezone.now(),
        )
        mechanical = JobPosting.objects.create(
            source="usajobs",
            source_job_id="mech-eng",
            title="Mechanical Engineer - Facilities",
            company_name="Agency",
            description_clean="HVAC and facilities engineering responsibilities.",
            category_normalized="Engineering",
            job_url="https://example.com/mech-eng",
            content_hash="mech-eng-hash",
            posted_at=timezone.now(),
        )
        query = "backend engineer"
        self.assertTrue(
            is_relevant_semantic_match(
                query,
                software_engineer,
                hybrid_score=0.5,
                lexical_score=compute_lexical_score(query, software_engineer),
                semantic_score=0.47,
            )
        )
        self.assertFalse(
            is_relevant_semantic_match(
                query,
                mechanical,
                hybrid_score=0.5,
                lexical_score=compute_lexical_score(query, mechanical),
                semantic_score=0.47,
            )
        )

    def test_narrow_semantic_search_expands_tiny_backend_pool(self):
        backend_job = JobPosting.objects.create(
            source="remotive",
            source_job_id="tiny-backend",
            title="Senior Full-stack React Developer",
            description_clean="Build backend APIs and React frontends for SaaS products.",
            job_url="https://example.com/tiny-backend",
            content_hash="tiny-backend-hash",
            posted_at=timezone.now(),
        )
        software_job = JobPosting.objects.create(
            source="adzuna",
            source_job_id="tiny-software",
            title="Software Engineer",
            description_clean="Application development across the stack.",
            job_url="https://example.com/tiny-software",
            content_hash="tiny-software-hash",
            posted_at=timezone.now(),
        )
        terms = prefilter_terms("backend engineer")
        narrow_ids = set(
            narrow_jobs_by_terms(JobPosting.objects.all(), terms).values_list("id", flat=True)
        )
        semantic_ids = set(
            narrow_jobs_for_semantic_search(JobPosting.objects.all(), terms).values_list(
                "id", flat=True
            )
        )
        self.assertIn(backend_job.id, narrow_ids)
        self.assertNotIn(software_job.id, narrow_ids)
        self.assertIn(software_job.id, semantic_ids)

    def test_backend_engineer_fallback_keeps_software_role_with_backend_in_body(self):
        staff_software = JobPosting.objects.create(
            source="remotive",
            source_job_id="staff-sw-1",
            title="Staff Software Engineer",
            company_name="LawnStarter",
            description_clean=(
                "Lead platform initiatives across product teams. "
                "Mentor engineers and drive technical strategy."
            ),
            category_normalized="Software Development",
            job_url="https://example.com/staff-sw",
            content_hash="staff-sw-hash",
            posted_at=timezone.now(),
        )
        software_backend = JobPosting.objects.create(
            source="remotive",
            source_job_id="sw-backend-1",
            title="Senior Software Engineer",
            company_name="A.Team",
            description_clean=(
                "Build backend APIs and scalable services for client products. "
                "Python, REST, and cloud deployment experience required."
            ),
            category_normalized="Software Development",
            job_url="https://example.com/sw-backend",
            content_hash="sw-backend-hash",
            posted_at=timezone.now(),
        )
        query = "backend engineer"
        specific = specific_query_terms(prefilter_terms(query))
        self.assertTrue(is_misleading_engineer_listing(staff_software, specific))
        self.assertFalse(is_misleading_engineer_listing(software_backend, specific))

        reranked = rerank_semantic_candidates(
            query,
            [
                {"job": staff_software, "semantic_score": 0.66},
                {"job": software_backend, "semantic_score": 0.55},
            ],
        )
        relevant, used_fallback = apply_relevance_with_fallback(query, reranked)
        self.assertTrue(used_fallback)
        self.assertGreaterEqual(len(relevant), 1)
        self.assertEqual(relevant[0]["job"].id, software_backend.id)
        self.assertNotIn(staff_software.id, {row["job"].id for row in relevant})

    def test_narrow_prefilter_requires_specific_terms_not_role_and(self):
        backend_job = JobPosting.objects.create(
            source="adzuna",
            source_job_id="be-narrow",
            title="Backend Engineer",
            description_clean="Build backend APIs and services with Python and SQL for production systems.",
            job_url="https://example.com/be-narrow",
            content_hash="be-narrow-hash",
            posted_at=timezone.now(),
        )
        engineer_only = JobPosting.objects.create(
            source="adzuna",
            source_job_id="eng-only",
            title="Staff Software Engineer",
            description_clean="Lead engineers and mentor teams across the organization on platform work.",
            job_url="https://example.com/eng-only",
            content_hash="eng-only-hash",
            posted_at=timezone.now(),
        )
        terms = prefilter_terms("backend engineer")
        ids = set(narrow_jobs_by_terms(JobPosting.objects.all(), terms).values_list("id", flat=True))
        self.assertIn(backend_job.id, ids)
        # Role-only rows without 'backend' are excluded from the narrow SQL scope.
        self.assertNotIn(engineer_only.id, ids)

    def test_role_alignment_prefers_title_phrase_match(self):
        backend_job = JobPosting.objects.create(
            source="adzuna",
            source_job_id="role-be",
            title="Backend Engineer",
            description_clean="Design REST APIs and backend services.",
            job_url="https://example.com/role-be",
            content_hash="role-be-hash",
            posted_at=timezone.now(),
        )
        generic_job = JobPosting.objects.create(
            source="adzuna",
            source_job_id="role-gen",
            title="Software Engineer",
            description_clean="General application development across the stack.",
            job_url="https://example.com/role-gen",
            content_hash="role-gen-hash",
            posted_at=timezone.now(),
        )
        query = "backend engineer"
        self.assertGreater(
            compute_role_alignment_score(query, backend_job),
            compute_role_alignment_score(query, generic_job),
        )

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
        self.assertEqual(retrieval_query_text("python developer"), "python developer")
        self.assertEqual(
            retrieval_query_text("backend engineer"),
            "backend developer software engineer",
        )

    def test_clerk_and_psychiatrist_rejected_for_python_long_query(self):
        clerk_job = JobPosting.objects.create(
            source="usajobs",
            source_job_id="clerk-2",
            title="Program Support Assistant (OA)",
            company_name="VA",
            description_clean=(
                "Enter data into systems and provide administrative support for work orders."
            ),
            category_normalized="Miscellaneous Clerk And Assistant",
            job_url="https://example.com/clerk-2",
            content_hash="clerk-hash-2",
            posted_at=timezone.now(),
        )
        psych_job = JobPosting.objects.create(
            source="adzuna",
            source_job_id="psych-2",
            title="Locums Psychiatrist",
            company_name="Weatherby Healthcare",
            description_clean="Healthcare psychiatrist role treating patients in outpatient clinic.",
            category_normalized="Healthcare & Nursing Jobs",
            job_url="https://example.com/psych-2",
            content_hash="psych-hash-2",
            posted_at=timezone.now(),
        )
        long_query = (
            "Python developer with backend experience building REST APIs, "
            "web services, and data-driven applications"
        )
        terms = prefilter_terms(long_query)
        qs = narrow_jobs_by_terms(JobPosting.objects.all(), terms)
        ids = set(qs.values_list("id", flat=True))
        self.assertIn(self.real_job.id, ids)
        self.assertNotIn(clerk_job.id, ids)
        self.assertNotIn(psych_job.id, ids)

    def test_query_term_prefilter_narrows_pgvector_scope(self):
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
        terms = prefilter_terms(long_query)
        qs = narrow_jobs_by_terms(JobPosting.objects.all(), terms)
        ids = set(qs.values_list("id", flat=True))
        self.assertIn(self.real_job.id, ids)
        self.assertNotIn(truck_job.id, ids)

    @override_settings(SEMANTIC_TECH_ONLY=True)
    @patch("apps.search.services.semantic_search.embed_text_with_metadata")
    @patch("apps.search.services.semantic_search.JobEmbedding")
    def test_semantic_search_excludes_demo_source(self, mock_embedding_model, mock_embed):
        from apps.search.services.embeddings.types import EmbeddingResult

        mock_embed.return_value = EmbeddingResult(
            vector=[0.0] * 384,
            provider_name="local",
            model_name="hashing-v1",
            dimension=384,
            configured_provider="local",
        )
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
