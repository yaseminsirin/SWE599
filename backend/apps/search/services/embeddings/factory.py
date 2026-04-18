from django.conf import settings

from .providers import BaseEmbeddingProvider, LocalHashEmbeddingProvider


def get_embedding_provider() -> BaseEmbeddingProvider:
    provider_name = settings.EMBEDDING_PROVIDER.lower()
    model_name = settings.EMBEDDING_MODEL_NAME
    dimension = settings.EMBEDDING_DIMENSION

    if provider_name == "local":
        return LocalHashEmbeddingProvider(
            model_name=model_name,
            vector_dimension=dimension,
        )

    raise ValueError(f"Unsupported embedding provider: {provider_name}")
