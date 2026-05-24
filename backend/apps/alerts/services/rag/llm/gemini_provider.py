import os

import requests
from django.conf import settings

from .base import BaseLLMProvider


class GeminiLLMProvider(BaseLLMProvider):
    provider_name = "gemini"
    api_base = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self) -> None:
        self.api_key = (
            getattr(settings, "GEMINI_API_KEY", "")
            or os.getenv("GEMINI_API_KEY", "")
        ).strip()
        self.model = (
            settings.LLM_MODEL or os.getenv("LLM_MODEL", "") or "gemini-2.0-flash"
        ).strip()
        self.timeout = settings.LLM_TIMEOUT_SECONDS

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(self, *, system: str, user: str) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured")

        url = f"{self.api_base}/{self.model}:generateContent"
        response = requests.post(
            url,
            params={"key": self.api_key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 500,
                },
            },
            timeout=self.timeout,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError(f"Gemini returned non-JSON response: {response.text[:200]}") from exc

        if response.status_code >= 400:
            message = _api_error_message(payload) or response.text[:300]
            raise ValueError(f"Gemini API error ({response.status_code}): {message}")

        api_error = _api_error_message(payload)
        if api_error:
            raise ValueError(f"Gemini API error: {api_error}")

        candidates = payload.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini returned no candidates")

        candidate = candidates[0]
        finish_reason = candidate.get("finishReason")
        if finish_reason and finish_reason not in {"STOP", "MAX_TOKENS"}:
            raise ValueError(f"Gemini blocked generation (finishReason={finish_reason})")

        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        texts = [part.get("text", "") for part in parts if part.get("text")]
        combined = "\n".join(texts).strip()
        if not combined:
            raise ValueError("Gemini returned empty content")
        return combined


def _api_error_message(payload: dict) -> str:
    error = payload.get("error")
    if not error:
        return ""
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error)
