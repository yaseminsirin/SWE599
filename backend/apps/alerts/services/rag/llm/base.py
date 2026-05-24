from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    provider_name: str = ""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when this provider is configured and reachable enough to try."""

    @abstractmethod
    def generate(self, *, system: str, user: str) -> str:
        """Return model text completion."""
