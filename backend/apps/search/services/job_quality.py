"""Quality and scope filters for searchable real API job postings."""

from __future__ import annotations

import re
from datetime import datetime

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
