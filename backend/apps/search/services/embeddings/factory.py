import logging

from django.conf import settings

from .providers import (
    BaseEmbeddingProvider,
    GeminiEmbeddingProvider,
    LocalHashEmbeddingProvider,
    LocalSentenceTransformerEmbeddingProvider,
)
from .types import EmbeddingProviderError, EmbeddingResult

logger = logging.getLogger(__name__)

FALLBACK_MODEL_NAME = "hashing-v1-fallback"
SENTENCE_TRANSFORMER_ALIASES = {"sentence_transformers", "sentence-transformers", "minilm"}


def is_embedding_strict_mode() -> bool:
    return bool(getattr(settings, "EMBEDDING_STRICT_PROVIDER", False))


def get_embedding_provider() -> BaseEmbeddingProvider:
    provider_name = settings.EMBEDDING_PROVIDER.lower().strip()
    model_name = settings.EMBEDDING_MODEL_NAME
    dimension = settings.EMBEDDING_DIMENSION

    if provider_name in SENTENCE_TRANSFORMER_ALIASES:
        return LocalSentenceTransformerEmbeddingProvider(
            model_name=model_name,
            vector_dimension=dimension,
        )

    if provider_name == "gemini":
        gemini = GeminiEmbeddingProvider(
            model_name=model_name,
            vector_dimension=dimension,
        )
        if gemini.is_available():
            return gemini
        if is_embedding_strict_mode():
            raise EmbeddingProviderError(
                "EMBEDDING_STRICT_PROVIDER is enabled but Gemini is not available "
                "(missing or empty GEMINI_API_KEY)."
            )
        logger.warning(
            "GEMINI_API_KEY missing or empty; using local hash embedding fallback "
            "(dimension=%s). Semantic quality will be limited.",
            dimension,
        )
        return LocalHashEmbeddingProvider(
            model_name=FALLBACK_MODEL_NAME,
            vector_dimension=dimension,
        )

    if provider_name == "local":
        return LocalHashEmbeddingProvider(
            model_name=model_name,
            vector_dimension=dimension,
        )

    raise ValueError(f"Unsupported embedding provider: {provider_name}")


def _call_embed(
    provider: BaseEmbeddingProvider,
    text: str,
    task_type: str | None,
) -> list[float]:
    try:
        return provider.embed_text(text, task_type=task_type)
    except TypeError:
        return provider.embed_text(text)


def embed_text_with_metadata(text: str, *, task_type: str | None = None) -> EmbeddingResult:
    """
    Embed text and report which provider actually produced the vector.
    Sentence-transformer and strict mode never fall back to hash embeddings.
    """
    configured = settings.EMBEDDING_PROVIDER.lower().strip()
    provider = get_embedding_provider()
    provider_substituted = configured == "gemini" and provider.provider_name != "gemini"

    if provider_substituted:
        if is_embedding_strict_mode():
            raise EmbeddingProviderError(
                "EMBEDDING_STRICT_PROVIDER is enabled but Gemini is not available "
                "(missing or empty GEMINI_API_KEY)."
            )
        logger.warning(
            "Configured embedding provider is gemini but active provider is %s/%s.",
            provider.provider_name,
            provider.model_name,
        )

    if provider.provider_name != "gemini":
        try:
            vector = _call_embed(provider, text, task_type)
        except Exception as exc:
            if is_embedding_strict_mode() or provider.provider_name == "sentence_transformers":
                raise EmbeddingProviderError(
                    f"Embedding failed for provider {provider.provider_name}: {exc}"
                ) from exc
            raise
        return EmbeddingResult(
            vector=vector,
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            dimension=len(vector),
            configured_provider=configured,
            provider_substituted=provider_substituted,
        )

    try:
        vector = _call_embed(provider, text, task_type)
        return EmbeddingResult(
            vector=vector,
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            dimension=len(vector),
            configured_provider=configured,
        )
    except Exception as exc:
        if is_embedding_strict_mode():
            raise EmbeddingProviderError(
                f"Gemini embedding failed and EMBEDDING_STRICT_PROVIDER is enabled: {exc}"
            ) from exc
        logger.warning(
            "Gemini embedding failed (%s); using local hash fallback for this request.",
            exc,
            exc_info=True,
        )
        fallback = LocalHashEmbeddingProvider(
            model_name=FALLBACK_MODEL_NAME,
            vector_dimension=settings.EMBEDDING_DIMENSION,
        )
        vector = fallback.embed_text(text)
        return EmbeddingResult(
            vector=vector,
            provider_name=fallback.provider_name,
            model_name=fallback.model_name,
            dimension=len(vector),
            configured_provider=configured,
            fallback_triggered=True,
            error_message=str(exc),
        )


def log_embedding_usage(
    result: EmbeddingResult,
    *,
    context: str,
    text_preview: str = "",
) -> None:
    preview = (text_preview or "")[:80].replace("\n", " ")
    logger.info(
        "%s embedding provider=%s model=%s dimension=%d fallback=%s substituted=%s "
        "configured=%s preview=%r%s",
        context,
        result.provider_name,
        result.model_name,
        result.dimension,
        result.fallback_triggered,
        result.provider_substituted,
        result.configured_provider,
        preview,
        f" error={result.error_message!r}" if result.error_message else "",
    )


def embed_text(text: str, *, task_type: str | None = None) -> list[float]:
    """Backward-compatible helper returning only the vector."""
    return embed_text_with_metadata(text, task_type=task_type).vector
