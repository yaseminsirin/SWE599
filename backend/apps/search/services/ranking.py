import re
from typing import Any

from django.conf import settings
from django.db.models import Count, QuerySet

from apps.jobs.models import JobPosting
from apps.search.services.job_quality import is_quality_job
from apps.search.models import JobEmbedding
from apps.search.services.embeddings.factory import (
    embed_text_with_metadata,
    is_embedding_strict_mode,
    log_embedding_usage,
)
from apps.search.services.embeddings.types import EmbeddingProviderError
from apps.search.services.vector_query import cosine_distance_annotation, semantic_score_from_row
from apps.tracking.models import JobClickEvent


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def compute_keyword_score(query: str, job: JobPosting) -> float:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0.0
    content_tokens = _tokenize(f"{job.title} {job.description_clean}")
    if not content_tokens:
        return 0.0
    overlap = len(q_tokens.intersection(content_tokens))
    return overlap / max(len(q_tokens), 1)


def _build_semantic_score_map(
    jobs: list[JobPosting],
    query_vector: list[float],
    *,
    provider_name: str,
    model_name: str,
) -> dict[int, float]:
    if not jobs or not query_vector:
        return {}

    job_ids = [job.id for job in jobs]
    rows = (
        JobEmbedding.objects.filter(
            job_id__in=job_ids,
            provider=provider_name,
            model_name=model_name,
        )
        .annotate(**cosine_distance_annotation(query_vector))
    )
    return {row.job_id: semantic_score_from_row(row) for row in rows}


def _build_click_score_map(jobs: list[JobPosting], user) -> dict[int, float]:
    job_ids = [job.id for job in jobs]
    base_query = JobClickEvent.objects.filter(job_id__in=job_ids)
    if getattr(user, "is_authenticated", False):
        user_counts = (
            base_query.filter(user=user)
            .values("job_id")
            .annotate(total=Count("id"))
        )
        user_map = {row["job_id"]: row["total"] for row in user_counts}
        max_user = max(user_map.values()) if user_map else 0
        if max_user > 0:
            return {job_id: count / max_user for job_id, count in user_map.items()}

    global_counts = (
        base_query.values("job_id")
        .annotate(total=Count("id"))
    )
    global_map = {row["job_id"]: row["total"] for row in global_counts}
    max_global = max(global_map.values()) if global_map else 0
    if max_global == 0:
        return {}
    return {job_id: count / max_global for job_id, count in global_map.items()}


def rank_jobs(queryset: QuerySet[JobPosting], *, query: str, user=None, limit: int = 50) -> list[dict[str, Any]]:
    jobs = [job for job in queryset[: limit * 2] if is_quality_job(job)][:limit]
    if not jobs:
        return []

    semantic_score_map: dict[int, float] = {}
    if query.strip():
        try:
            embed_result = embed_text_with_metadata(query, task_type="RETRIEVAL_QUERY")
            log_embedding_usage(embed_result, context="ranked_search_query", text_preview=query)
            if is_embedding_strict_mode() and (
                embed_result.fallback_triggered or embed_result.provider_substituted
            ):
                raise EmbeddingProviderError(
                    embed_result.error_message or "embedding provider unavailable"
                )
            semantic_score_map = _build_semantic_score_map(
                jobs,
                embed_result.vector,
                provider_name=embed_result.provider_name,
                model_name=embed_result.model_name,
            )
        except EmbeddingProviderError:
            semantic_score_map = {}
    click_score_map = _build_click_score_map(jobs, user)

    wk = settings.RANKING_WEIGHT_KEYWORD
    ws = settings.RANKING_WEIGHT_SEMANTIC
    wc = settings.RANKING_WEIGHT_CLICK
    weight_sum = wk + ws + wc
    if weight_sum <= 0:
        wk, ws, wc = 1.0, 0.0, 0.0
        weight_sum = 1.0
    wk, ws, wc = wk / weight_sum, ws / weight_sum, wc / weight_sum

    ranked: list[dict[str, Any]] = []
    for job in jobs:
        keyword_score = compute_keyword_score(query, job)
        semantic_score = semantic_score_map.get(job.id, 0.0)
        click_score = click_score_map.get(job.id, 0.0)
        final_score = (wk * keyword_score) + (ws * semantic_score) + (wc * click_score)
        ranked.append(
            {
                "job": job,
                "keyword_score": keyword_score,
                "semantic_score": semantic_score,
                "click_score": click_score,
                "final_score": final_score,
            }
        )

    ranked.sort(key=lambda row: (row["final_score"], row["job"].posted_at or row["job"].created_at), reverse=True)
    for idx, row in enumerate(ranked, start=1):
        row["rank_position"] = idx
    return ranked
