"""Quality and scope filters for searchable real API job postings."""

from __future__ import annotations

import re
from datetime import datetime

# Whole-word matching avoids false positives (e.g. engineer vs "Engineering Service").
WORD_BOUNDARY_TOKENS = frozenset({"engineer", "developer", "analyst"})

from django.conf import settings
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.jobs.models import JobPosting

REAL_JOB_SOURCES = ("adzuna", "usajobs", "remotive")
EXCLUDED_SEARCH_SOURCES = ("demo",)

TECH_SIGNAL_TERMS = (
    "software",
    "developer",
    "engineer",
    "engineering",
    "programmer",
    "python",
    "django",
    "react",
    "javascript",
    "typescript",
    "frontend",
    "backend",
    "full-stack",
    "full stack",
    "devops",
    "data scientist",
    "data analyst",
    "machine learning",
    "ml ",
    " ai ",
    "cloud",
    "api",
    "database",
    "sql",
    "kubernetes",
    "aws",
    "web developer",
    "mobile",
    "ios",
    "android",
    "product analyst",
    "business analyst",
    "analyst",
    "saas",
    "platform",
)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def is_quality_job(job: JobPosting) -> bool:
    title = (job.title or "").strip()
    description = (job.description_clean or job.description_raw or "").strip()
    if len(title) < 4:
        return False
    if len(description) < 80:
        return False
    if "example.invalid" in (job.job_url or ""):
        return False
    if job.expires_at and job.expires_at < timezone.now():
        return False
    return True


def is_tech_related_job(job: JobPosting) -> bool:
    haystack = " ".join(
        [
            job.title or "",
            job.normalized_title or "",
            job.description_clean or "",
            job.category_normalized or "",
            job.category_raw or "",
        ]
    ).lower()
    return any(term in haystack for term in TECH_SIGNAL_TERMS)


def get_searchable_job_queryset(
    *,
    real_sources_only: bool = True,
    exclude_demo: bool = True,
    tech_only: bool | None = None,
) -> QuerySet[JobPosting]:
    queryset = JobPosting.objects.all()
    if real_sources_only:
        queryset = queryset.filter(source__in=REAL_JOB_SOURCES)
    if exclude_demo:
        queryset = queryset.exclude(source__in=EXCLUDED_SEARCH_SOURCES)
    if tech_only is None:
        tech_only = getattr(settings, "SEMANTIC_TECH_ONLY", True)
    if tech_only:
        tech_q = Q()
        for term in TECH_SIGNAL_TERMS:
            tech_q |= Q(title__icontains=term)
            tech_q |= Q(normalized_title__icontains=term)
            tech_q |= Q(description_clean__icontains=term)
            tech_q |= Q(category_normalized__icontains=term)
        queryset = queryset.filter(tech_q)
    return queryset


def apply_keyword_token_filter(queryset: QuerySet[JobPosting], keyword: str) -> QuerySet[JobPosting]:
    """Match any query token in title, normalized title, or description (not whole phrase only)."""
    tokens = _tokenize(keyword)
    if not tokens:
        return queryset
    token_q = Q()
    for token in tokens:
        token_q |= Q(title__icontains=token)
        token_q |= Q(normalized_title__icontains=token)
        token_q |= Q(description_clean__icontains=token)
    return queryset.filter(token_q)


def _term_lookup_q(token: str) -> Q:
    """Build OR conditions for one prefilter token."""
    if token in WORD_BOUNDARY_TOKENS:
        pattern = rf"\m{re.escape(token)}\M"
        return (
            Q(title__iregex=pattern)
            | Q(normalized_title__iregex=pattern)
            | Q(description_clean__iregex=pattern)
            | Q(category_normalized__iregex=pattern)
            | Q(category_raw__iregex=pattern)
        )
    if len(token) <= 4:
        return (
            Q(title__istartswith=token)
            | Q(normalized_title__istartswith=token)
            | Q(category_normalized__istartswith=token)
            | Q(category_raw__istartswith=token)
        )
    return (
        Q(title__icontains=token)
        | Q(normalized_title__icontains=token)
        | Q(description_clean__icontains=token)
        | Q(category_normalized__icontains=token)
        | Q(category_raw__icontains=token)
    )


# Mirror retrieval_rerank role/broad tokens for AND-style prefilter (avoid circular imports).
_PREFILTER_GENERIC_ROLE_TERMS = frozenset(
    {"engineer", "developer", "programmer", "analyst", "scientist", "architect", "software"}
)
_PREFILTER_GENERIC_BROAD_TERMS = frozenset(
    {"data", "web", "api", "apis", "cloud", "mobile", "ai", "ml", "sql"}
)


def _prefilter_specific_terms(terms: set[str]) -> set[str]:
    return terms - _PREFILTER_GENERIC_ROLE_TERMS - _PREFILTER_GENERIC_BROAD_TERMS


SEMANTIC_STACK_SCOPE_MIN_JOBS = 25

SOFTWARE_SCOPE_TERMS = frozenset(
    {
        "software",
        "developer",
        "programmer",
        "fullstack",
        "computer",
        "devops",
        "cloud",
        "web",
        "backend",
        "frontend",
        "python",
        "java",
        "react",
        "javascript",
        "typescript",
        "cyber",
        "cybersecurity",
    }
)


def _queryset_meets_min_rows(queryset: QuerySet[JobPosting], minimum: int) -> bool:
    if minimum <= 0:
        return True
    return (
        len(list(queryset.values_list("id", flat=True)[: minimum + 1]))
        >= minimum
    )


def semantic_retrieval_terms(terms: set[str]) -> set[str]:
    """Widen tiny stack-only SQL scopes to software roles for vector retrieval."""
    specific = _prefilter_specific_terms(terms)
    if specific and len(terms) >= 2:
        return set(specific) | SOFTWARE_SCOPE_TERMS
    return terms


def narrow_jobs_by_terms_broad(queryset: QuerySet[JobPosting], terms: set[str]) -> QuerySet[JobPosting]:
    """Match any query token (OR) — wider recall fallback."""
    if not terms:
        return queryset
    token_q = Q()
    for token in sorted(terms):
        token_q |= _term_lookup_q(token)
    return queryset.filter(token_q)


def narrow_jobs_by_terms(queryset: QuerySet[JobPosting], terms: set[str]) -> QuerySet[JobPosting]:
    """
    Narrow pgvector scope before vector search.

    Multi-term queries AND only specific stack tokens (e.g. backend). Generic role
    words (engineer, developer) are enforced in rerank/relevance, not SQL — otherwise
    'backend engineer' often matches zero rows while index-first fills with Staff roles.
    """
    if not terms:
        return queryset

    specific = _prefilter_specific_terms(terms)
    if specific and len(terms) >= 2:
        narrowed = queryset
        for token in sorted(specific):
            narrowed = narrowed.filter(_term_lookup_q(token))
        return narrowed

    return narrow_jobs_by_terms_broad(queryset, terms)


def narrow_jobs_for_semantic_search(
    queryset: QuerySet[JobPosting],
    terms: set[str],
) -> QuerySet[JobPosting]:
    """
    SQL scope before pgvector.

    Stack + role queries (backend engineer) AND on specific tokens first; when that
    corpus is tiny on real data, widen to software-role OR terms so retrieval is not
    limited to a dozen remotive rows that mention 'backend' in the body.
    """
    if not terms:
        return queryset

    specific = _prefilter_specific_terms(terms)
    if specific and len(terms) >= 2:
        narrowed = narrow_jobs_by_terms(queryset, terms)
        if _queryset_meets_min_rows(narrowed, SEMANTIC_STACK_SCOPE_MIN_JOBS):
            return narrowed
        return narrow_jobs_by_terms_broad(queryset, semantic_retrieval_terms(terms))

    return narrow_jobs_by_terms(queryset, terms)
