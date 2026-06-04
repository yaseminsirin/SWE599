import logging
from typing import Any

from django.conf import settings

from apps.search.models import JobEmbedding

from .embeddings.factory import (
    EmbeddingProviderError,
    embed_text_with_metadata,
    is_embedding_strict_mode,
    log_embedding_usage,
)
from .job_quality import get_searchable_job_queryset, is_quality_job, narrow_jobs_by_terms
from .retrieval_rerank import (
    apply_relevance_with_fallback,
    is_natural_language_query,
    prefilter_terms,
    rerank_semantic_candidates,
    retrieval_query_text,
    should_skip_pgvector_prefilter,
)
from .vector_query import cosine_distance_annotation, semantic_score_from_row

logger = logging.getLogger(__name__)


def _query_prefilter_terms(query: str) -> set[str]:
    return prefilter_terms(query)


def _pgvector_candidates(
    *,
    query_vector: list[float],
    index_provider: str,
    index_model: str,
    job_ids,
    pool_size: int,
) -> list[dict[str, Any]]:
    rows = (
        JobEmbedding.objects.filter(
            job_id__in=job_ids,
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
    return candidates


def semantic_search_jobs(
    query: str,
    *,
    top_k: int = 20,
    tech_only: bool | None = None,
) -> list[dict[str, Any]]:
    """
    pgvector retrieval with optional query-term prefilter (short queries only),
    hybrid rerank, relevance gate, and NL fallback.
    """
    natural_language = is_natural_language_query(query)
    terms = _query_prefilter_terms(query)
    retrieval_text = retrieval_query_text(query)

    embed_result = embed_text_with_metadata(retrieval_text, task_type="RETRIEVAL_QUERY")
    log_embedding_usage(
        embed_result,
        context="semantic_search_query",
        text_preview=f"{query} -> {retrieval_text}",
    )

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

    base_qs = get_searchable_job_queryset(
        real_sources_only=True,
        exclude_demo=True,
        tech_only=tech_only,
    )
    pool_size = int(getattr(settings, "SEMANTIC_SEARCH_CANDIDATE_POOL", 200))

    skip_prefilter = should_skip_pgvector_prefilter(query)
    if skip_prefilter:
        narrowed_qs = base_qs
    else:
        narrowed_qs = narrow_jobs_by_terms(base_qs, terms) if terms else base_qs
    count_before_pgvector = narrowed_qs.count()
    job_ids = narrowed_qs.values_list("id", flat=True)

    candidates = _pgvector_candidates(
        query_vector=query_vector,
        index_provider=index_provider,
        index_model=index_model,
        job_ids=job_ids,
        pool_size=pool_size,
    )

    if not candidates and terms and not skip_prefilter:
        count_before_pgvector = base_qs.count()
        job_ids = base_qs.values_list("id", flat=True)
        candidates = _pgvector_candidates(
            query_vector=query_vector,
            index_provider=index_provider,
            index_model=index_model,
            job_ids=job_ids,
            pool_size=pool_size,
        )

    reranked = rerank_semantic_candidates(query, candidates)
    relevant, used_fallback = apply_relevance_with_fallback(query, reranked)

    logger.info(
        "semantic_search query=%r natural_language=%s retrieval_text=%r prefilter_terms=%s "
        "candidates_before_pgvector=%s after_pgvector=%s after_rerank=%s after_relevance=%s fallback=%s",
        query,
        natural_language,
        retrieval_text,
        sorted(terms),
        count_before_pgvector,
        len(candidates),
        len(reranked),
        len(relevant),
        used_fallback,
    )

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
