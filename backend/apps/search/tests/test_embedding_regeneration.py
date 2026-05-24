from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.jobs.models import JobPosting
from apps.search.models import JobEmbedding
from apps.search.services.embedding_generation import (
    get_embedding_candidate_queryset,
    regenerate_job_embeddings,
)
from apps.search.services.embeddings.types import EmbeddingProviderError


class EmbeddingRegenerationTests(TestCase):
    def setUp(self):
        self.remotive = JobPosting.objects.create(
            source="remotive",
            source_job_id="r-1",
            title="Python Developer Remote",
            company_name="Remote Co",
            description_clean="python django api " * 10,
            job_url="https://example.com/r/1",
            content_hash="r-hash-1",
        )
        self.usajobs = JobPosting.objects.create(
            source="usajobs",
            source_job_id="u-1",
            title="Software Engineer",
            company_name="Gov",
            description_clean="python backend services " * 10,
            job_url="https://example.com/u/1",
            content_hash="u-hash-1",
        )

    def test_candidate_queryset_orders_remotive_before_usajobs(self):
        ordered = list(
            get_embedding_candidate_queryset(tech_only=True).values_list("source", flat=True)
        )
        self.assertEqual(ordered[0], "remotive")
        self.assertIn("usajobs", ordered)

    @override_settings(
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_MODEL_NAME="gemini-embedding-001",
        EMBEDDING_DIMENSION=768,
        GEMINI_API_KEY="test-key",
        EMBEDDING_STRICT_PROVIDER=True,
        EMBEDDING_STOP_ON_QUOTA=True,
    )
    @patch("apps.search.services.embedding_generation.embed_text_with_metadata")
    def test_regenerate_stops_on_quota_in_strict_mode(self, mock_embed):
        mock_embed.side_effect = EmbeddingProviderError(
            "Gemini embedding failed and EMBEDDING_STRICT_PROVIDER is enabled: "
            "Gemini embedding API error (429): Resource exhausted"
        )
        summary = regenerate_job_embeddings(tech_only=True, limit=5, sleep_seconds=0)
        self.assertEqual(summary["regenerated"], 0)
        self.assertGreater(summary["errors"], 0)
        self.assertTrue(summary["stopped_on_quota"])
        self.assertEqual(JobEmbedding.objects.count(), 0)

    @override_settings(
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_MODEL_NAME="gemini-embedding-001",
        EMBEDDING_DIMENSION=768,
        GEMINI_API_KEY="test-key",
    )
    @patch("apps.search.services.embedding_generation.embed_text_with_metadata")
    def test_regenerate_respects_limit(self, mock_embed):
        mock_embed.return_value = MagicMock(
            vector=[0.1] * 768,
            provider_name="gemini",
            model_name="gemini-embedding-001",
            dimension=768,
            configured_provider="gemini",
            fallback_triggered=False,
            provider_substituted=False,
        )
        summary = regenerate_job_embeddings(tech_only=True, limit=1, sleep_seconds=0)
        self.assertEqual(summary["regenerated"], 1)
        self.assertEqual(JobEmbedding.objects.count(), 1)
