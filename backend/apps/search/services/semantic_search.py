import logging
import time
from collections import OrderedDict
from typing import Any

from django.conf import settings
from django.db.models import Q, QuerySet
from django.db.models.functions import Length

from apps.jobs.models import JobPosting
from apps.search.models import JobEmbedding

from .embeddings.factory import (
    EmbeddingProviderError,
    embed_text_with_metadata,
    get_embedding_provider,
    is_embedding_strict_mode,
    log_embedding_usage,
)
from .embeddings.types import EmbeddingResult
from .job_quality import (
    EXCLUDED_SEARCH_SOURCES,
    REAL_JOB_SOURCES,
    TECH_SIGNAL_TERMS,
    get_searchable_job_queryset,
    is_quality_job,
    narrow_jobs_by_terms,
)
from .retrieval_rerank import (
    apply_relevance_with_fallback,
    is_natural_language_query,
    prefilter_terms,
    rerank_semantic_candidates,
    retrieval_query_text,
    should_skip_pgvector_prefilter,
)
from .vector_query import cosine_distance_annotation, semantic_score_from_row, with_hnsw_ef_search

logger = logging.getLogger(__name__)

_QUERY_EMBED_CACHE: OrderedDict[str, EmbeddingResult] = OrderedDict()
_QUERY_EMBED_CACHE_MAX = 128

_SCOPE_IDS_CACHE: dict[tuple[Any, ...], tuple[float, frozenset[int]]] = {}
_SCOPE_IDS_CACHE_TTL = 300.0
_SCOPE_IDS_CACHE_MAX = 32

_JOB_HYDRATE_FIELDS = (
    "id",
    "source",
    "title",
    "normalized_title",
    "company_name",
    "description_clean",
    "description_raw",
    "category_normalized",
    "category_raw",
    "job_url",
    "expires_at",
    "posted_at",
    "created_at",
    "location_text",
    "city",
    "country",
    "is_remote",
    "employment_type",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
)


def _query_prefilter_terms(query: str) -> set[str]:
    return prefilter_terms(query)


def _pgvector_scan_limit(pool_size: int, *, narrowed_size: int | None = None) -> int:
    multiplier = int(getattr(settings, "SEMANTIC_SEARCH_SCAN_MULTIPLIER", 10))
    floor = int(getattr(settings, "SEMANTIC_SEARCH_SCAN_FLOOR", 120))
    cap = int(getattr(settings, "SEMANTIC_SEARCH_SCAN_CAP", 600))

    if narrowed_size is not None and narrowed_size > 0:
        # Tight prefilter — scan a small multiple of the narrowed corpus.
        narrowed_cap = int(getattr(settings, "SEMANTIC_SEARCH_NARROWED_SCAN_CAP", 250))
        return min(max(pool_size * 3, min(narrowed_size * 4, narrowed_cap)), narrowed_cap)

    return min(max(pool_size * max(multiplier, 1), floor), cap)


def _large_corpus_threshold() -> int:
    return int(getattr(settings, "SEMANTIC_SEARCH_INDEX_FIRST_MIN_SCOPE", 6000))


def _scope_cache_key(job_scope: QuerySet[JobPosting]) -> tuple[Any, ...]:
    return ("scope", job_scope.query)


def _materialize_job_ids(job_scope: QuerySet[JobPosting]) -> frozenset[int]:
    """Cache narrowed scope IDs briefly — prefilter iregex queries are expensive."""
    cache_key = _scope_cache_key(job_scope)
    now = time.monotonic()
    cached = _SCOPE_IDS_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _SCOPE_IDS_CACHE_TTL:
        return cached[1]

    ids = frozenset(job_scope.values_list("id", flat=True))
    _SCOPE_IDS_CACHE[cache_key] = (now, ids)
    while len(_SCOPE_IDS_CACHE) > _SCOPE_IDS_CACHE_MAX:
        _SCOPE_IDS_CACHE.pop(next(iter(_SCOPE_IDS_CACHE)))
    return ids


def _embedding_scope_queryset(
    *,
    index_provider: str,
    index_model: str,
    tech_only: bool | None,
) -> QuerySet[JobEmbedding]:
    """SQL join filters for the searchable corpus — avoids materializing 10k+ IDs per request."""
    queryset = JobEmbedding.objects.filter(
        provider=index_provider,
        model_name=index_model,
        job__source__in=REAL_JOB_SOURCES,
    ).exclude(job__source__in=EXCLUDED_SEARCH_SOURCES)

    if tech_only is None:
        tech_only = getattr(settings, "SEMANTIC_TECH_ONLY", True)
    if tech_only:
        tech_q = Q()
        for term in TECH_SIGNAL_TERMS:
            tech_q |= Q(job__title__icontains=term)
            tech_q |= Q(job__normalized_title__icontains=term)
            tech_q |= Q(job__description_clean__icontains=term)
            tech_q |= Q(job__category_normalized__icontains=term)
        queryset = queryset.filter(tech_q)

    return queryset.annotate(
        job_desc_len=Length("job__description_clean"),
    ).filter(
        job_desc_len__gte=80,
    ).exclude(
        job__job_url__icontains="example.invalid",
    )


def _embed_query_cached(retrieval_text: str) -> EmbeddingResult:
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


def _pgvector_neighbor_rows(
    *,
    queryset: QuerySet[JobEmbedding],
    query_vector: list[float],
    scan_limit: int,
    job_ids: frozenset[int] | None = None,
) -> list[dict[str, Any]]:
    """
    Lightweight ANN: fetch only job_id + distance (no job row hydration).
    """
    use_index_first = job_ids is None or len(job_ids) >= _large_corpus_threshold()
    scoped = queryset
    if not use_index_first and job_ids:
        scoped = scoped.filter(job_id__in=job_ids)

    with with_hnsw_ef_search():
        return list(
            scoped.annotate(**cosine_distance_annotation(query_vector))
            .order_by("distance")
            .values("job_id", "distance")[:scan_limit]
        )


def _hydrate_jobs(job_ids: list[int]) -> dict[int, JobPosting]:
    if not job_ids:
        return {}
    rows = JobPosting.objects.filter(id__in=job_ids).only(*_JOB_HYDRATE_FIELDS)
    return {job.id: job for job in rows}


def _collect_candidates(
    neighbor_rows: list[dict[str, Any]],
    *,
    allowed_ids: frozenset[int] | None,
    pool_size: int,
    jobs_by_id: dict[int, JobPosting],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in neighbor_rows:
        job_id = int(row["job_id"])
        if allowed_ids is not None and job_id not in allowed_ids:
            continue
        job = jobs_by_id.get(job_id)
        if job is None or not is_quality_job(job):
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
    scope_queryset: QuerySet[JobEmbedding],
    query_vector: list[float],
    allowed_ids: frozenset[int] | None,
    pool_size: int,
    scan_limit: int,
    prefer_ids: frozenset[int] | None = None,
) -> list[dict[str, Any]]:
    use_prefer_fallback = (
        prefer_ids is not None and prefer_ids and prefer_ids != allowed_ids
    )
    threshold = _large_corpus_threshold()
    if use_prefer_fallback:
        search_ids = None
    elif prefer_ids and len(prefer_ids) < threshold:
        search_ids = prefer_ids
    elif allowed_ids is not None and len(allowed_ids) < threshold:
        search_ids = allowed_ids
    else:
        search_ids = None

    neighbor_rows = _pgvector_neighbor_rows(
        queryset=scope_queryset,
        query_vector=query_vector,
        scan_limit=scan_limit,
        job_ids=search_ids,
    )
    if not neighbor_rows:
        return []

    hydrate_order: list[int] = []
    seen: set[int] = set()
    for row in neighbor_rows:
        job_id = int(row["job_id"])
        if job_id in seen:
            continue
        seen.add(job_id)
        hydrate_order.append(job_id)
        if len(hydrate_order) >= scan_limit:
            break

    jobs_by_id = _hydrate_jobs(hydrate_order)

    if use_prefer_fallback:
        candidates = _collect_candidates(
            neighbor_rows,
            allowed_ids=prefer_ids,
            pool_size=pool_size,
            jobs_by_id=jobs_by_id,
        )
        if candidates:
            return candidates
        return _collect_candidates(
            neighbor_rows,
            allowed_ids=allowed_ids,
            pool_size=pool_size,
            jobs_by_id=jobs_by_id,
        )

    return _collect_candidates(
        neighbor_rows,
        allowed_ids=allowed_ids,
        pool_size=pool_size,
        jobs_by_id=jobs_by_id,
    )


def warmup_embedding_model() -> None:
    """Load sentence-transformers once at process start (avoids multi-second first search)."""
    try:
        provider = get_embedding_provider()
        if hasattr(provider, "_encode"):
            provider._encode(["search warmup"])
            logger.info("embedding_model_warmup_ok provider=%s", provider.provider_name)
    except Exception as exc:
        logger.warning("embedding_model_warmup_failed error=%s", exc)


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

    scope_queryset = _embedding_scope_queryset(
        index_provider=index_provider,
        index_model=index_model,
        tech_only=tech_only,
    )
    pool_size = min(
        int(getattr(settings, "SEMANTIC_SEARCH_CANDIDATE_POOL", 100)),
        max(top_k * 2, top_k),
    )

    skip_prefilter = should_skip_pgvector_prefilter(query)
    narrowed_ids: frozenset[int] | None = None
    if not skip_prefilter:
        base_qs = get_searchable_job_queryset(
            real_sources_only=True,
            exclude_demo=True,
            tech_only=tech_only,
        )
        narrowed_qs = narrow_jobs_by_terms(base_qs, terms) if terms else base_qs
        narrowed_ids = _materialize_job_ids(narrowed_qs)

    scan_limit = _pgvector_scan_limit(
        pool_size,
        narrowed_size=len(narrowed_ids) if narrowed_ids is not None else None,
    )

    candidates: list[dict[str, Any]] = []
    scope_size = 0

    if skip_prefilter:
        scope_size = -1  # join-scoped corpus; no ID materialization
        candidates = _pgvector_candidates(
            scope_queryset=scope_queryset,
            query_vector=query_vector,
            allowed_ids=None,
            pool_size=pool_size,
            scan_limit=scan_limit,
        )
    elif narrowed_ids is not None:
        scope_size = len(narrowed_ids)
        if narrowed_ids:
            candidates = _pgvector_candidates(
                scope_queryset=scope_queryset,
                query_vector=query_vector,
                allowed_ids=None,
                prefer_ids=narrowed_ids,
                pool_size=pool_size,
                scan_limit=scan_limit,
            )

    if not candidates and terms and not skip_prefilter:
        from .job_quality import narrow_jobs_by_terms_broad

        logger.warning(
            "semantic_search narrow prefilter returned no candidates; "
            "retrying with broad OR prefilter terms=%s",
            sorted(terms),
        )
        base_qs = get_searchable_job_queryset(
            real_sources_only=True,
            exclude_demo=True,
            tech_only=tech_only,
        )
        broad_ids = _materialize_job_ids(narrow_jobs_by_terms_broad(base_qs, terms))
        scope_size = len(broad_ids)
        scan_limit = _pgvector_scan_limit(pool_size, narrowed_size=len(broad_ids) or None)
        candidates = _pgvector_candidates(
            scope_queryset=scope_queryset,
            query_vector=query_vector,
            allowed_ids=broad_ids or None,
            pool_size=pool_size,
            scan_limit=scan_limit,
        )

    if not candidates and skip_prefilter and terms:
        logger.warning(
            "semantic_search pgvector returned no quality candidates for NL query; "
            "retrying with query-term prefilter terms=%s",
            sorted(terms),
        )
        base_qs = get_searchable_job_queryset(
            real_sources_only=True,
            exclude_demo=True,
            tech_only=tech_only,
        )
        term_ids = _materialize_job_ids(narrow_jobs_by_terms(base_qs, terms))
        scope_size = len(term_ids)
        scan_limit = _pgvector_scan_limit(pool_size, narrowed_size=len(term_ids))
        candidates = _pgvector_candidates(
            scope_queryset=scope_queryset,
            query_vector=query_vector,
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
