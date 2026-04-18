from typing import Any

from apps.jobs.models import JobPosting
from apps.search.models import JobEmbedding

from .embeddings.factory import get_embedding_provider
from .similarity import cosine_similarity


def semantic_search_jobs(query: str, *, top_k: int = 20) -> list[dict[str, Any]]:
    provider = get_embedding_provider()
    query_vector = provider.embed_text(query)

    embeddings = (
        JobEmbedding.objects.filter(
            provider=provider.provider_name,
            model_name=provider.model_name,
        )
        .select_related("job")
    )

    scored: list[dict[str, Any]] = []
    for item in embeddings:
        score = cosine_similarity(query_vector, item.embedding)
        scored.append(
            {
                "job": item.job,
                "semantic_score": score,
            }
        )

    scored.sort(key=lambda row: row["semantic_score"], reverse=True)
    return scored[:top_k]


def get_jobs_missing_embeddings(*, limit: int = 200) -> list[JobPosting]:
    provider = get_embedding_provider()
    return list(
        JobPosting.objects.exclude(
            embeddings__provider=provider.provider_name,
            embeddings__model_name=provider.model_name,
        )
        .order_by("-posted_at", "-created_at")[:limit]
    )
