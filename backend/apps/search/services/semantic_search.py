from typing import Any

from django.conf import settings

from apps.search.models import JobEmbedding

from .embeddings.factory import (
    EmbeddingProviderError,
    embed_text_with_metadata,
    is_embedding_strict_mode,
    log_embedding_usage,
)
from .job_quality import get_searchable_job_queryset, is_quality_job
from .retrieval_rerank import filter_relevant_semantic_results, rerank_semantic_candidates
from .vector_query import cosine_distance_annotation, semantic_score_from_row


def semantic_search_jobs(
    query: str,
    *,
    top_k: int = 20,
    tech_only: bool | None = None,
) -> list[dict[str, Any]]:
    """
    pgvector first-stage retrieval on real API jobs, then lightweight hybrid rerank.
    Excludes demo seed data by default.
    """
    embed_result = embed_text_with_metadata(query, task_type="RETRIEVAL_QUERY")
    log_embedding_usage(embed_result, context="semantic_search_query", text_preview=query)

    if is_embedding_strict_mode() and (
        embed_result.fallback_triggered or embed_result.provider_substituted
    ):
        detail = embed_result.error_message or "provider unavailable"
        raise EmbeddingProviderError(
            f"Semantic search blocked: {detail} (EMBEDDING_STRICT_PROVIDER=true)"
        )

    query_vector = embed_result.vector
    index_provider = embed_result.provider_name
    index_model = embed_result.model_name

    searchable_ids = get_searchable_job_queryset(
        real_sources_only=True,
        exclude_demo=True,
        tech_only=tech_only,
    ).values_list("id", flat=True)

    pool_size = int(getattr(settings, "SEMANTIC_SEARCH_CANDIDATE_POOL", 100))

    rows = (
        JobEmbedding.objects.filter(
            job_id__in=searchable_ids,
            provider=index_provider,
            model_name=index_model,
        )
        .annotate(**cosine_distance_annotation(query_vector))
        .select_related("job")
        .order_by("distance")[:pool_size]
    )

    candidates: list[dict[str, Any]] = []
    for row in rows:
        job = row.job
        if not is_quality_job(job):
            continue
        candidates.append(
            {
                "job": job,
                "semantic_score": semantic_score_from_row(row),
            }
        )

    reranked = rerank_semantic_candidates(query, candidates)
    relevant = filter_relevant_semantic_results(query, reranked)
    return relevant[:top_k]


def get_jobs_missing_embeddings(*, limit: int = 200, source: str | None = None) -> list:
    from .embedding_generation import get_embedding_candidate_queryset

    tech_only = getattr(settings, "EMBEDDING_TECH_ONLY", None)
    if tech_only is None:
        tech_only = getattr(settings, "SEMANTIC_TECH_ONLY", True)

    queryset = get_embedding_candidate_queryset(
        source=source,
        tech_only=tech_only,
        missing_only=True,
    )
    return list(queryset[:limit])
