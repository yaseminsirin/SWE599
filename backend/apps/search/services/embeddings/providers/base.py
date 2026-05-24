from abc import ABC, abstractmethod


class BaseEmbeddingProvider(ABC):
    provider_name: str = ""
    model_name: str = ""
    vector_dimension: int = 0

    def is_available(self) -> bool:
        return True

    @abstractmethod
    def embed_text(self, text: str, *, task_type: str | None = None) -> list[float]:
        """Generate embedding vector for one text input."""
