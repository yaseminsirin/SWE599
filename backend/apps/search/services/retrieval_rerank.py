"""Lightweight lexical reranking on top of pgvector semantic candidates."""

from __future__ import annotations

from typing import Any

from django.conf import settings

from apps.jobs.models import JobPosting

from .job_quality import _tokenize

SEARCH_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "for",
        "with",
        "to",
        "in",
        "on",
        "at",
        "of",
        "is",
        "are",
        "be",
        "as",
        "by",
        "from",
        "that",
        "this",
        "i",
        "am",
        "looking",
        "role",
        "roles",
        "job",
        "jobs",
        "work",
        "experience",
        "experienced",
        "building",
        "modern",
        "teams",
        "team",
        "services",
        "service",
        "applications",
        "application",
        "driven",
        "based",
        "using",
        "use",
        "new",
        "our",
        "your",
        "you",
        "we",
        "will",
        "can",
        "have",
        "has",
        "who",
        "what",
        "when",
        "where",
        "how",
        "all",
        "any",
        "per",
        "via",
        "into",
        "over",
        "under",
        "about",
        "than",
        "then",
        "them",
        "they",
        "their",
        "there",
        "these",
        "those",
        "not",
        "but",
        "also",
        "etc",
        "etc.",
    }
)


def content_tokens(text: str) -> set[str]:
    return {token for token in _tokenize(text) if len(token) >= 3 and token not in SEARCH_STOPWORDS}


def compute_lexical_score(query: str, job: JobPosting) -> float:
    q_tokens = content_tokens(query)
    if not q_tokens:
        return 0.0

    title_tokens = content_tokens(job.title or "")
    norm_title_tokens = content_tokens(job.normalized_title or "")
    body_tokens = content_tokens(job.description_clean or "")
    category_tokens = content_tokens(
        " ".join(filter(None, [job.category_normalized, job.category_raw]))
    )

    title_overlap = len(q_tokens.intersection(title_tokens)) / len(q_tokens)
    norm_overlap = len(q_tokens.intersection(norm_title_tokens)) / len(q_tokens)
    body_overlap = len(q_tokens.intersection(body_tokens)) / len(q_tokens)
    category_overlap = len(q_tokens.intersection(category_tokens)) / len(q_tokens)

    return min(
        1.0,
        (0.50 * title_overlap)
        + (0.25 * norm_overlap)
        + (0.15 * body_overlap)
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


def is_relevant_semantic_match(
    query: str,
    job: JobPosting,
    *,
    hybrid_score: float,
    lexical_score: float,
) -> bool:
    """Drop cross-domain pgvector neighbors (e.g. truck driver for a Python query)."""
    q_terms = content_tokens(query)
    if not q_terms:
        return hybrid_score >= 0.35

    title_terms = content_tokens(" ".join(filter(None, [job.title, job.normalized_title])))
    category_terms = content_tokens(
        " ".join(filter(None, [job.category_normalized, job.category_raw]))
    )
    body_terms = content_tokens(job.description_clean or "")

    title_hits = q_terms & title_terms
    category_hits = q_terms & category_terms
    body_hits = q_terms & body_terms

    if title_hits or category_hits:
        return True

    if len(body_hits) >= 2 and lexical_score >= 0.06:
        return True

    if body_hits and hybrid_score >= 0.40 and lexical_score >= 0.05:
        return True

    if hybrid_score >= 0.52 and lexical_score >= 0.08:
        return True

    return False


def filter_relevant_semantic_results(
    query: str,
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not results:
        return []
    return [
        item
        for item in results
        if is_relevant_semantic_match(
            query,
            item["job"],
            hybrid_score=float(item.get("hybrid_score", item["semantic_score"])),
            lexical_score=float(item.get("lexical_score", 0.0)),
        )
    ]
