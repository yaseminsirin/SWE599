import os

import requests
from django.conf import settings

from .base import BaseLLMProvider


class OpenAILLMProvider(BaseLLMProvider):
    provider_name = "openai"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = (settings.LLM_MODEL or os.getenv("LLM_MODEL", "") or "gpt-4o-mini").strip()
        self.timeout = settings.LLM_TIMEOUT_SECONDS

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(self, *, system: str, user: str) -> str:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured")

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.3,
                "max_tokens": 500,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError("OpenAI returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if not str(content).strip():
            raise ValueError("OpenAI returned empty content")
        return str(content).strip()
