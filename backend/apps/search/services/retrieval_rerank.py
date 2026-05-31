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


TECH_QUERY_SIGNALS = frozenset(
    {
        "python",
        "django",
        "flask",
        "react",
        "java",
        "javascript",
        "typescript",
        "developer",
        "engineer",
        "software",
        "backend",
        "frontend",
        "devops",
        "data",
        "sql",
        "api",
        "apis",
        "cloud",
        "fullstack",
        "mobile",
        "ios",
        "android",
        "ml",
        "ai",
        "kubernetes",
        "aws",
    }
)

# Too broad for SQL prefilter / title gate — match unrelated clerk & healthcare listings.
GENERIC_BROAD_TERMS = frozenset({"data", "web", "api", "apis", "cloud", "mobile", "ai", "ml", "sql"})

STRONG_ROLE_TERMS = frozenset(
    {
        "python",
        "django",
        "flask",
        "react",
        "java",
        "javascript",
        "typescript",
        "developer",
        "engineer",
        "software",
        "backend",
        "frontend",
        "devops",
        "programmer",
        "fullstack",
        "kubernetes",
        "aws",
        "analyst",
        "scientist",
    }
)

IT_CATEGORY_HINTS = (
    "information technology",
    "software",
    "computer",
    "engineering",
    "developer",
    "programmer",
    "data science",
    "cyber",
)

NON_TECH_JOB_PHRASES = (
    "truck driver",
    "cdl",
    "owner operator",
    "delivery driver",
    "flatbed",
    "logistics",
    "warehouse",
    "security officer",
    "forklift",
    "janitor",
    "cashier",
    "nurse aide",
    "psychiatrist",
    "program support assistant",
    "miscellaneous clerk",
    "healthcare",
    "registered nurse",
    "medical assistant",
)


def content_tokens(text: str) -> set[str]:
    return {token for token in _tokenize(text) if len(token) >= 3 and token not in SEARCH_STOPWORDS}


def is_tech_query(query: str) -> bool:
    return bool(content_tokens(query) & TECH_QUERY_SIGNALS)


def prefilter_terms(query: str) -> set[str]:
    """Terms used to narrow pgvector — avoid generic tokens like data/web."""
    terms = core_query_terms(query) or content_tokens(query)
    if not terms:
        return set()
    if is_tech_query(query):
        strong = terms & STRONG_ROLE_TERMS
        if strong:
            return strong
    specific = terms - GENERIC_BROAD_TERMS
    return specific if specific else terms


def match_terms_for_relevance(query: str) -> set[str]:
    terms = core_query_terms(query) or content_tokens(query)
    if is_tech_query(query):
        strong = terms & STRONG_ROLE_TERMS
        if strong:
            return strong
    return terms


def core_query_terms(query: str, *, max_terms: int = 6) -> set[str]:
    """Focus lexical/relevance checks on the most specific query terms."""
    terms = content_tokens(query)
    if not terms:
        return set()
    if len(terms) <= max_terms:
        return terms
    return set(sorted(terms, key=lambda token: (-len(token), token))[:max_terms])


def retrieval_query_text(query: str) -> str:
    """
    Compact text for embedding / pgvector retrieval.

    Long natural-language queries embed far from short job-title vectors; use strong
    role/skill terms so detailed searches behave like focused keyword queries.
    """
    stripped = (query or "").strip()
    if not stripped:
        return ""
    strong = prefilter_terms(stripped)
    if strong:
        return " ".join(sorted(strong))
    word_count = len(stripped.split())
    terms = core_query_terms(stripped)
    if word_count > 5 and terms:
        return " ".join(sorted(terms - GENERIC_BROAD_TERMS or terms))
    if len(terms) >= 2:
        return " ".join(sorted(terms))
    return stripped


def _job_text_blob(job: JobPosting) -> str:
    return " ".join(
        filter(
            None,
            [
                job.title,
                job.normalized_title,
                job.category_normalized,
                job.category_raw,
                (job.description_clean or "")[:500],
            ],
        )
    ).lower()


def is_domain_mismatch(query: str, job: JobPosting) -> bool:
    """Drop obvious cross-domain neighbors (e.g. truck driver for a Python query)."""
    q_terms = content_tokens(query)
    if not q_terms & TECH_QUERY_SIGNALS:
        return False

    blob = _job_text_blob(job)
    job_terms = content_tokens(blob)
    if job_terms & TECH_QUERY_SIGNALS:
        return False

    return any(phrase in blob for phrase in NON_TECH_JOB_PHRASES)


def compute_lexical_score(query: str, job: JobPosting) -> float:
    q_tokens = core_query_terms(query)
    if not q_tokens:
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
    semantic_score: float,
) -> bool:
    if is_domain_mismatch(query, job):
        return False

    q_terms = match_terms_for_relevance(query)
    if not q_terms:
        return semantic_score >= 0.35

    title_terms = content_tokens(" ".join(filter(None, [job.title, job.normalized_title])))
    category_terms = content_tokens(
        " ".join(filter(None, [job.category_normalized, job.category_raw]))
    )
    body_terms = content_tokens(job.description_clean or "")
    category_blob = " ".join(filter(None, [job.category_normalized, job.category_raw])).lower()

    title_hits = q_terms & title_terms
    category_hits = q_terms & category_terms
    body_hits = q_terms & body_terms

    if is_tech_query(query):
        if title_hits:
            return True
        if category_hits and any(hint in category_blob for hint in IT_CATEGORY_HINTS):
            return True
        if len(body_hits) >= 2 and semantic_score >= 0.42 and lexical_score >= 0.08:
            return True
        return False

    if title_hits or category_hits:
        return True
    if body_hits and semantic_score >= 0.38:
        return True
    if body_hits and hybrid_score >= 0.35:
        return True
    return semantic_score >= 0.48 and lexical_score >= 0.04


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
            semantic_score=float(item.get("semantic_score", 0.0)),
        )
    ]
