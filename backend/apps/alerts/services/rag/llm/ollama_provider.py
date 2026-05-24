import os

import requests
from django.conf import settings

from .base import BaseLLMProvider


class OllamaLLMProvider(BaseLLMProvider):
    provider_name = "ollama"

    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.model = (settings.LLM_MODEL or os.getenv("LLM_MODEL", "") or "llama3.2").strip()
        self.timeout = settings.LLM_TIMEOUT_SECONDS

    def is_available(self) -> bool:
        return bool(self.base_url and self.model)

    def generate(self, *, system: str, user: str) -> str:
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": 0.3},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        message = payload.get("message") or {}
        content = message.get("content", "")
        if not str(content).strip():
            raise ValueError("Ollama returned empty content")
        return str(content).strip()
