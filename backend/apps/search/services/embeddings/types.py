from dataclasses import dataclass


class EmbeddingProviderError(Exception):
    """Embedding unavailable or strict mode rejected a fallback."""


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]
    provider_name: str
    model_name: str
    dimension: int
    configured_provider: str
    fallback_triggered: bool = False
    provider_substituted: bool = False
    error_message: str | None = None

    @property
    def used_primary_provider(self) -> bool:
        return not self.fallback_triggered and not self.provider_substituted
