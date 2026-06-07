import logging
from collections import OrderedDict
from typing import Any

from django.conf import settings
from django.db.models import QuerySet

from apps.jobs.models import JobPosting
from apps.search.models import JobEmbedding

from .embeddings.factory import (
    EmbeddingProviderError,
    embed_text_with_metadata,
    is_embedding_strict_mode,
    log_embedding_usage,
)
from .embeddings.types import EmbeddingResult
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

_QUERY_EMBED_CACHE: OrderedDict[str, EmbeddingResult] = OrderedDict()
_QUERY_EMBED_CACHE_MAX = 128


def _query_prefilter_terms(query: str) -> set[str]:
    return prefilter_terms(query)


def _pgvector_scan_limit(pool_size: int) -> int:
    """
    Fetch more than pool_size pgvector neighbors so we can skip low-quality rows.

    On production USAJOBS-heavy indexes, the nearest vectors are often short/noisy
    postings that fail is_quality_job; scanning only pool_size rows yields zero results.
    """
    multiplier = int(getattr(settings, "SEMANTIC_SEARCH_SCAN_MULTIPLIER", 15))
    floor = int(getattr(settings, "SEMANTIC_SEARCH_SCAN_FLOOR", 300))
    cap = int(getattr(settings, "SEMANTIC_SEARCH_SCAN_CAP", 1500))
    return min(max(pool_size * max(multiplier, 1), floor), cap)


def _large_corpus_threshold() -> int:
    return int(getattr(settings, "SEMANTIC_SEARCH_INDEX_FIRST_MIN_SCOPE", 6000))


def _materialize_job_ids(job_scope: QuerySet[JobPosting]) -> set[int]:
    """One-shot ID set — avoids repeating slow job__in subqueries on every pgvector call."""
    return set(job_scope.values_list("id", flat=True))


def _embed_query_cached(retrieval_text: str) -> EmbeddingResult:
    """Cache query embeddings; only the query is embedded per search, never job postings."""
    cached = _QUERY_EMBED_CACHE.get(retrieval_text)
    if cached is not None:
        _QUERY_EMBED_CACHE.move_to_end(retrieval_text)
        return cached

    result = embed_text_with_metadata(retrieval_text, task_type="RETRIEVAL_QUERY")
    _QUERY_EMBED_CACHE[retrieval_text] = result
    _QUERY_EMBED_CACHE.move_to_end(retrieval_text)
    while len(_QUERY_EMBED_CACHE) > _QUERY_EMBED_CACHE_MAX:
        _QUERY_EMBED_CACHE.popitem(last=False)
    return result


def _pgvector_rows(
    *,
    query_vector: list[float],
    index_provider: str,
    index_model: str,
    scan_limit: int,
    job_ids: set[int] | None = None,
) -> list[JobEmbedding]:
    """
    Nearest-neighbor fetch using the HNSW index.

    When job_ids is None or larger than the index-first threshold, filter only by
    provider/model so PostgreSQL can use the vector index. Otherwise use a
    materialized job_id__in list (faster than a correlated job__in subquery).
    """
    queryset = JobEmbedding.objects.filter(
        provider=index_provider,
        model_name=index_model,
    )
    use_index_first = job_ids is None or len(job_ids) >= _large_corpus_threshold()
    if not use_index_first and job_ids:
        queryset = queryset.filter(job_id__in=job_ids)

    return list(
        queryset.annotate(**cosine_distance_annotation(query_vector))
        .select_related("job")
        .order_by("distance")[:scan_limit]
    )


def _collect_candidates(
    rows: list[JobEmbedding],
    *,
    allowed_ids: set[int],
    pool_size: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        job = row.job
        if job.id not in allowed_ids or not is_quality_job(job):
            continue
        candidates.append(
            {
                "job": job,
                "semantic_score": semantic_score_from_row(row),
            }
        )
        if len(candidates) >= pool_size:
            break
    return candidates


def _pgvector_candidates(
    *,
    query_vector: list[float],
    index_provider: str,
    index_model: str,
    allowed_ids: set[int],
    pool_size: int,
    scan_limit: int,
    prefer_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve semantic neighbors for a materialized job scope.

    When prefer_ids is a strict subset of allowed_ids, one pgvector round-trip tries
    the preferred scope first, then falls back to the wider allowed_ids on the same rows.
    """
    if not allowed_ids:
        return []

    use_prefer_fallback = (
        prefer_ids is not None and prefer_ids and prefer_ids != allowed_ids
    )
    search_ids = allowed_ids if use_prefer_fallback else (prefer_ids or allowed_ids)

    rows = _pgvector_rows(
        query_vector=query_vector,
        index_provider=index_provider,
        index_model=index_model,
        scan_limit=scan_limit,
        job_ids=search_ids,
    )

    if use_prefer_fallback:
        candidates = _collect_candidates(rows, allowed_ids=prefer_ids, pool_size=pool_size)
        if candidates:
            return candidates

    return _collect_candidates(rows, allowed_ids=allowed_ids, pool_size=pool_size)


def semantic_search_jobs(
    query: str,
    *,
    top_k: int = 20,
    tech_only: bool | None = None,
) -> list[dict[str, Any]]:
    """
    pgvector retrieval with optional query-term prefilter (short queries only),
    hybrid rerank, relevance gate, and NL fallback.

    Job embeddings are precomputed in JobEmbedding; each request embeds only the query.
    """
    natural_language = is_natural_language_query(query)
    terms = _query_prefilter_terms(query)
    retrieval_text = retrieval_query_text(query)

    embed_result = _embed_query_cached(retrieval_text)
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
    scan_limit = _pgvector_scan_limit(pool_size)
    base_ids = _materialize_job_ids(base_qs)

    skip_prefilter = should_skip_pgvector_prefilter(query)
    narrowed_ids: set[int] | None = None
    if not skip_prefilter:
        narrowed_qs = narrow_jobs_by_terms(base_qs, terms) if terms else base_qs
        narrowed_ids = _materialize_job_ids(narrowed_qs)

    candidates: list[dict[str, Any]] = []
    scope_size = 0

    if skip_prefilter:
        scope_size = len(base_ids)
        candidates = _pgvector_candidates(
            query_vector=query_vector,
            index_provider=index_provider,
            index_model=index_model,
            allowed_ids=base_ids,
            pool_size=pool_size,
            scan_limit=scan_limit,
        )
    elif narrowed_ids is not None:
        scope_size = len(narrowed_ids)
        candidates = _pgvector_candidates(
            query_vector=query_vector,
            index_provider=index_provider,
            index_model=index_model,
            allowed_ids=base_ids,
            prefer_ids=narrowed_ids,
            pool_size=pool_size,
            scan_limit=scan_limit,
        )

    if not candidates and terms and not skip_prefilter and narrowed_ids is not None:
        scope_size = len(base_ids)
        candidates = _pgvector_candidates(
            query_vector=query_vector,
            index_provider=index_provider,
            index_model=index_model,
            allowed_ids=base_ids,
            pool_size=pool_size,
            scan_limit=scan_limit,
        )

    if not candidates and skip_prefilter and terms:
        logger.warning(
            "semantic_search pgvector returned no quality candidates for NL query; "
            "retrying with query-term prefilter terms=%s",
            sorted(terms),
        )
        term_ids = _materialize_job_ids(narrow_jobs_by_terms(base_qs, terms))
        scope_size = len(term_ids)
        candidates = _pgvector_candidates(
            query_vector=query_vector,
            index_provider=index_provider,
            index_model=index_model,
            allowed_ids=term_ids,
            pool_size=pool_size,
            scan_limit=scan_limit,
        )

    reranked = rerank_semantic_candidates(query, candidates)
    relevant, used_fallback = apply_relevance_with_fallback(query, reranked)

    logger.info(
        "semantic_search query=%r natural_language=%s retrieval_text=%r prefilter_terms=%s "
        "scope_jobs=%s after_pgvector=%s after_rerank=%s after_relevance=%s fallback=%s",
        query,
        natural_language,
        retrieval_text,
        sorted(terms),
        scope_size,
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
