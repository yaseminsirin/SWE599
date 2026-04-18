import re
from typing import Any

from django.conf import settings
from django.db.models import Count, QuerySet

from apps.jobs.models import JobPosting
from apps.search.models import JobEmbedding
from apps.search.services.embeddings.factory import get_embedding_provider
from apps.search.services.similarity import cosine_similarity
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


def _build_embedding_map(jobs: list[JobPosting]) -> dict[int, list[float]]:
    provider = get_embedding_provider()
    rows = JobEmbedding.objects.filter(
        job__in=jobs,
        provider=provider.provider_name,
        model_name=provider.model_name,
    )
    return {row.job_id: row.embedding for row in rows}


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
    jobs = list(queryset[:limit])
    if not jobs:
        return []

    provider = get_embedding_provider()
    query_vector = provider.embed_text(query)
    embedding_map = _build_embedding_map(jobs)
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
        semantic_score = 0.0
        job_vec = embedding_map.get(job.id)
        if job_vec:
            semantic_score = cosine_similarity(query_vector, job_vec)
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
