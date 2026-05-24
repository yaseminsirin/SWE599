import hashlib
import math
import re

from .base import BaseEmbeddingProvider


class LocalHashEmbeddingProvider(BaseEmbeddingProvider):
    provider_name = "local"

    def __init__(self, *, model_name: str = "hashing-v1", vector_dimension: int = 128) -> None:
        self.model_name = model_name
        self.vector_dimension = vector_dimension

    def embed_text(self, text: str, *, task_type: str | None = None) -> list[float]:
        tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
        vector = [0.0] * self.vector_dimension
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            idx = int(digest, 16) % self.vector_dimension
            vector[idx] += 1.0

        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            return vector
        return [v / norm for v in vector]
