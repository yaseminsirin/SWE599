from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from .base import BaseEmbeddingProvider

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_MODEL_LOCK = threading.Lock()
_MODEL_CACHE: dict[str, SentenceTransformer] = {}


def _load_model(model_name: str) -> SentenceTransformer:
    with _MODEL_LOCK:
        cached = _MODEL_CACHE.get(model_name)
        if cached is not None:
            return cached
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence-transformers model: %s", model_name)
        model = SentenceTransformer(model_name)
        _MODEL_CACHE[model_name] = model
        return model


class LocalSentenceTransformerEmbeddingProvider(BaseEmbeddingProvider):
    """Local embedding model (not an LLM) for pgvector semantic search."""

    provider_name = "sentence_transformers"

    def __init__(self, *, model_name: str, vector_dimension: int) -> None:
        self.model_name = model_name
        self.vector_dimension = vector_dimension

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = _load_model(self.model_name)
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        rows = [vector.tolist() for vector in vectors]
        for index, row in enumerate(rows):
            if len(row) != self.vector_dimension:
                raise ValueError(
                    f"Sentence-transformer dimension mismatch for {self.model_name}: "
                    f"got {len(row)}, expected {self.vector_dimension}"
                )
        return rows

    def embed_text(self, text: str, *, task_type: str | None = None) -> list[float]:
        del task_type  # MiniLM uses the same encoder for queries and documents.
        return self._encode([text or " "])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)
