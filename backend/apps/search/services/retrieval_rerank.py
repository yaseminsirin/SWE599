"""Lightweight lexical reranking on top of pgvector semantic candidates."""

from __future__ import annotations

import re
from typing import Any

from django.conf import settings

from apps.jobs.models import JobPosting

from .job_quality import _tokenize


def compute_lexical_score(query: str, job: JobPosting) -> float:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0.0

    title_tokens = _tokenize(job.title)
    norm_title_tokens = _tokenize(job.normalized_title)
    body_tokens = _tokenize(job.description_clean)
    category_tokens = _tokenize(job.category_normalized)

    title_overlap = len(q_tokens.intersection(title_tokens)) / len(q_tokens)
    norm_overlap = len(q_tokens.intersection(norm_title_tokens)) / len(q_tokens)
    body_overlap = len(q_tokens.intersection(body_tokens)) / len(q_tokens)
    category_overlap = len(q_tokens.intersection(category_tokens)) / len(q_tokens)

    # Title-heavy lexical signal for software queries on noisy corpora.
    return min(
        1.0,
        (0.45 * title_overlap)
        + (0.25 * norm_overlap)
        + (0.20 * body_overlap)
        + (0.10 * category_overlap),
    )


def compute_hybrid_score(*, semantic_score: float, lexical_score: float) -> float:
    ws = float(getattr(settings, "SEMANTIC_RERANK_WEIGHT_SEMANTIC", 0.7))
    wl = float(getattr(settings, "SEMANTIC_RERANK_WEIGHT_LEXICAL", 0.3))
    total = ws + wl
    if total <= 0:
        return semantic_score
    ws, wl = ws / total, wl / total
    return (ws * semantic_score) + (wl * lexical_score)


def rerank_semantic_candidates(
    query: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reranked: list[dict[str, Any]] = []
    for item in candidates:
        job = item["job"]
        semantic_score = float(item["semantic_score"])
        lexical_score = compute_lexical_score(query, job)
        hybrid_score = compute_hybrid_score(
            semantic_score=semantic_score,
            lexical_score=lexical_score,
        )
        reranked.append(
            {
                **item,
                "lexical_score": lexical_score,
                "hybrid_score": hybrid_score,
            }
        )
    reranked.sort(
        key=lambda row: (row["hybrid_score"], row["semantic_score"], row["job"].posted_at or row["job"].created_at),
        reverse=True,
    )
    return reranked
