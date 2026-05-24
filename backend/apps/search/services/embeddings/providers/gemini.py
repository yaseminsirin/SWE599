import requests
from django.conf import settings

from .base import BaseEmbeddingProvider


class GeminiEmbeddingProvider(BaseEmbeddingProvider):
    provider_name = "gemini"
    api_base = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, *, model_name: str, vector_dimension: int) -> None:
        self.api_key = getattr(settings, "GEMINI_API_KEY", "").strip()
        self.model_name = model_name
        self.vector_dimension = vector_dimension
        self.timeout = settings.LLM_TIMEOUT_SECONDS

    def is_available(self) -> bool:
        return bool(self.api_key and self.model_name)

    def embed_text(self, text: str, *, task_type: str | None = None) -> list[float]:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured")

        model_id = self.model_name
        if not model_id.startswith("models/"):
            model_id = f"models/{model_id}"

        url = f"{self.api_base}/{self.model_name}:embedContent"
        body: dict = {
            "model": model_id,
            "content": {"parts": [{"text": text or " "}]},
            "outputDimensionality": self.vector_dimension,
        }
        if task_type:
            body["taskType"] = task_type

        response = requests.post(
            url,
            params={"key": self.api_key},
            json=body,
            timeout=self.timeout,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError(
                f"Gemini embedding returned non-JSON: {response.text[:200]}"
            ) from exc

        if response.status_code >= 400:
            message = _api_error_message(payload) or response.text[:300]
            raise ValueError(f"Gemini embedding API error ({response.status_code}): {message}")

        api_error = _api_error_message(payload)
        if api_error:
            raise ValueError(f"Gemini embedding API error: {api_error}")

        embedding = payload.get("embedding") or {}
        values = embedding.get("values")
        if not isinstance(values, list) or not values:
            raise ValueError("Gemini embedding response missing embedding.values")

        vector = [float(v) for v in values]
        if len(vector) != self.vector_dimension:
            raise ValueError(
                f"Gemini embedding dimension mismatch: got {len(vector)}, "
                f"expected {self.vector_dimension}"
            )
        return vector


def _api_error_message(payload: dict) -> str:
    error = payload.get("error")
    if not error:
        return ""
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error)
