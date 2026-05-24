from unittest.mock import MagicMock, patch

import numpy as np
from django.test import TestCase, override_settings

from apps.search.services.embeddings.factory import embed_text_with_metadata, get_embedding_provider
from apps.search.services.embeddings.providers.sentence_transformer import (
    LocalSentenceTransformerEmbeddingProvider,
)


@override_settings(
    EMBEDDING_PROVIDER="sentence_transformers",
    EMBEDDING_MODEL_NAME="sentence-transformers/all-MiniLM-L6-v2",
    EMBEDDING_DIMENSION=384,
    EMBEDDING_STRICT_PROVIDER=True,
)
class SentenceTransformerEmbeddingTests(TestCase):
    def test_provider_selection(self):
        provider = get_embedding_provider()
        self.assertIsInstance(provider, LocalSentenceTransformerEmbeddingProvider)
        self.assertEqual(provider.vector_dimension, 384)

    @patch("apps.search.services.embeddings.providers.sentence_transformer._load_model")
    def test_embed_text_returns_384_dim_vector(self, mock_load):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 384])
        mock_load.return_value = mock_model

        provider = LocalSentenceTransformerEmbeddingProvider(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            vector_dimension=384,
        )
        vector = provider.embed_text("python backend developer")
        self.assertEqual(len(vector), 384)
        mock_model.encode.assert_called_once()

    @patch("apps.search.services.embeddings.providers.sentence_transformer._load_model")
    def test_embed_texts_batch(self, mock_load):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 384, [0.2] * 384])
        mock_load.return_value = mock_model

        provider = LocalSentenceTransformerEmbeddingProvider(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            vector_dimension=384,
        )
        vectors = provider.embed_texts(["python", "react"])
        self.assertEqual(len(vectors), 2)
        self.assertEqual(len(vectors[0]), 384)

    @patch("apps.search.services.embeddings.providers.sentence_transformer._load_model")
    def test_metadata_uses_sentence_transformer_provider(self, mock_load):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.3] * 384])
        mock_load.return_value = mock_model

        result = embed_text_with_metadata("django developer")
        self.assertEqual(result.provider_name, "sentence_transformers")
        self.assertEqual(result.dimension, 384)
        self.assertFalse(result.fallback_triggered)
