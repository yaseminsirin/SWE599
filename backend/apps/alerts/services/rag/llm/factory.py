from django.conf import settings

from .base import BaseLLMProvider
from .gemini_provider import GeminiLLMProvider
from .ollama_provider import OllamaLLMProvider
from .openai_provider import OpenAILLMProvider


def get_llm_provider() -> BaseLLMProvider | None:
    name = (settings.LLM_PROVIDER or "").strip().lower()
    if not name or name in {"none", "off", "disabled"}:
        return None
    if name == "openai":
        return OpenAILLMProvider()
    if name == "gemini":
        return GeminiLLMProvider()
    if name == "ollama":
        return OllamaLLMProvider()
    raise ValueError(f"Unsupported LLM_PROVIDER: {name}")
