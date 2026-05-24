from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.search.services.embeddings.factory import (
    embed_text,
    embed_text_with_metadata,
    get_embedding_provider,
)
from apps.search.services.embeddings.providers.gemini import GeminiEmbeddingProvider
from apps.search.services.embeddings.providers.local import LocalHashEmbeddingProvider
from apps.search.services.embeddings.types import EmbeddingProviderError
from apps.search.services.embedding_generation import generate_job_embedding
from apps.jobs.models import JobPosting


class GeminiEmbeddingProviderTests(TestCase):
    @override_settings(
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_MODEL_NAME="gemini-embedding-001",
        EMBEDDING_DIMENSION=768,
        GEMINI_API_KEY="test-key",
    )
    def test_provider_selection_gemini(self):
        provider = get_embedding_provider()
        self.assertIsInstance(provider, GeminiEmbeddingProvider)
        self.assertEqual(provider.model_name, "gemini-embedding-001")
        self.assertEqual(provider.vector_dimension, 768)

    @override_settings(
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_MODEL_NAME="gemini-embedding-001",
        EMBEDDING_DIMENSION=768,
        GEMINI_API_KEY="",
    )
    def test_missing_key_falls_back_to_local(self):
        provider = get_embedding_provider()
        self.assertIsInstance(provider, LocalHashEmbeddingProvider)
        vector = provider.embed_text("python backend")
        self.assertEqual(len(vector), 768)

    @override_settings(
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_MODEL_NAME="gemini-embedding-001",
        EMBEDDING_DIMENSION=768,
        GEMINI_API_KEY="test-key",
    )
    @patch("apps.search.services.embeddings.providers.gemini.requests.post")
    def test_gemini_response_parsing(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            text='{"embedding": {"values": [0.1, 0.2, 0.3]}}',
        )
        mock_post.return_value.json.return_value = {
            "embedding": {"values": [0.1] * 768},
        }

        provider = GeminiEmbeddingProvider(
            model_name="gemini-embedding-001",
            vector_dimension=768,
        )
        vector = provider.embed_text("python", task_type="RETRIEVAL_QUERY")
        self.assertEqual(len(vector), 768)
        mock_post.assert_called_once()
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["taskType"], "RETRIEVAL_QUERY")
        self.assertEqual(body["outputDimensionality"], 768)

    @override_settings(
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_MODEL_NAME="gemini-embedding-001",
        EMBEDDING_DIMENSION=768,
        GEMINI_API_KEY="test-key",
    )
    @patch("apps.search.services.embeddings.providers.gemini.requests.post")
    def test_runtime_failure_falls_back_to_local(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=500,
            text="error",
        )
        mock_post.return_value.json.return_value = {"error": {"message": "quota"}}

        result = embed_text_with_metadata("machine learning engineer")
        self.assertEqual(len(result.vector), 768)
        self.assertTrue(result.fallback_triggered)
        self.assertEqual(result.provider_name, "local")
        self.assertEqual(result.model_name, "hashing-v1-fallback")

    @override_settings(
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_MODEL_NAME="gemini-embedding-001",
        EMBEDDING_DIMENSION=768,
        GEMINI_API_KEY="test-key",
        EMBEDDING_STRICT_PROVIDER=True,
    )
    @patch("apps.search.services.embeddings.providers.gemini.requests.post")
    def test_strict_mode_raises_on_gemini_failure(self, mock_post):
        mock_post.return_value = MagicMock(status_code=429, text="quota")
        mock_post.return_value.json.return_value = {
            "error": {"message": "Resource exhausted"}
        }
        with self.assertRaises(EmbeddingProviderError):
            embed_text_with_metadata("python developer")

    @override_settings(
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_MODEL_NAME="gemini-embedding-001",
        EMBEDDING_DIMENSION=768,
        GEMINI_API_KEY="test-key",
    )
    @patch("apps.search.services.embeddings.factory.embed_text_with_metadata")
    def test_job_embedding_stores_actual_provider_on_fallback(self, mock_embed):
        mock_embed.return_value = MagicMock(
            vector=[0.1] * 768,
            provider_name="local",
            model_name="hashing-v1-fallback",
            dimension=768,
            configured_provider="gemini",
            fallback_triggered=True,
            provider_substituted=False,
            error_message="quota",
        )
        job = JobPosting.objects.create(
            source="adzuna",
            source_job_id="embed-fallback-1",
            title="Python Developer",
            company_name="Acme",
            description_clean="x" * 100,
            job_url="https://example.com/j/1",
            content_hash="hash-embed-fallback-1",
        )
        row = generate_job_embedding(job)
        self.assertEqual(row.provider, "local")
        self.assertEqual(row.model_name, "hashing-v1-fallback")
