from abc import ABC, abstractmethod


class BaseEmbeddingProvider(ABC):
    provider_name: str = ""
    model_name: str = ""
    vector_dimension: int = 0

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for one text input."""
