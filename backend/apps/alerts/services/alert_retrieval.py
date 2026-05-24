"""Retrieve jobs for alert emails using the platform search pipeline (not the LLM)."""

from __future__ import annotations

from typing import Any

from apps.jobs.models import JobPosting
from apps.jobs.services.job_labels import format_location_display
from apps.search.services.job_quality import get_searchable_job_queryset, is_quality_job
from apps.search.services.job_search import apply_job_filters
from apps.search.services.semantic_search import semantic_search_jobs

from ..models import AlertDeliveryLog, JobAlert


def _delivered_job_ids(alert: JobAlert) -> set[int]:
    return set(
        AlertDeliveryLog.objects.filter(alert=alert).values_list("job_id", flat=True)
    )


def _job_matches_alert_filters(job: JobPosting, alert: JobAlert) -> bool:
    if not is_quality_job(job):
        return False

    if alert.location_text:
        location = alert.location_text.lower()
        haystack = " ".join(
            filter(
                None,
                [job.location_text, job.city, job.country],
            )
        ).lower()
        if location not in haystack:
            return False

    if alert.is_remote is not None and job.is_remote != alert.is_remote:
        return False

    if alert.employment_type and (job.employment_type or "").lower() != alert.employment_type.lower():
        return False

    return True


def _filter_params_from_alert(alert: JobAlert) -> dict[str, str]:
    params: dict[str, str] = {}
    if alert.location_text:
        params["location"] = alert.location_text
    if alert.employment_type:
        params["employment_type"] = alert.employment_type
    if alert.is_remote is True:
        params["is_remote"] = "true"
    elif alert.is_remote is False:
        params["is_remote"] = "false"
    return params


def _semantic_ranked_jobs(alert: JobAlert, *, pool_size: int = 100) -> list[JobPosting]:
    query = (alert.keyword or "").strip()
    if not query:
        return []

    scored = semantic_search_jobs(query, top_k=pool_size, tech_only=True)
    jobs: list[JobPosting] = []
    for item in scored:
        job = item["job"]
        if _job_matches_alert_filters(job, alert):
            jobs.append(job)
    return jobs


def _keyword_ranked_jobs(alert: JobAlert, *, pool_size: int = 100) -> list[JobPosting]:
    queryset = get_searchable_job_queryset(
        real_sources_only=True,
        exclude_demo=True,
        tech_only=True,
    )
    params = _filter_params_from_alert(alert)
    if alert.keyword:
        params["keyword"] = alert.keyword
    queryset = apply_job_filters(queryset, params)
    return list(queryset[:pool_size])


def retrieve_alert_jobs(
    alert: JobAlert,
    *,
    min_results: int = 10,
    max_results: int = 20,
) -> list[JobPosting]:
    """
    Return up to max_results jobs for one alert email.

    Priority:
    1. Undelivered jobs new since last_notified_at (semantic/hybrid ranked)
    2. Otherwise undelivered top semantic/hybrid matches
  3. Otherwise keyword-filtered tech jobs not yet delivered
    """
    max_results = max(1, min(max_results, 20))
    min_results = max(1, min(min_results, max_results))
    delivered_ids = _delivered_job_ids(alert)

    ranked = _semantic_ranked_jobs(alert, pool_size=100)
    if not ranked and alert.keyword:
        ranked = _keyword_ranked_jobs(alert, pool_size=100)
    elif not ranked:
        ranked = _keyword_ranked_jobs(alert, pool_size=100)

    undelivered = [job for job in ranked if job.id not in delivered_ids]

    selected: list[JobPosting] = []
    if alert.last_notified_at:
        new_jobs = [
            job
            for job in undelivered
            if job.normalized_at and job.normalized_at > alert.last_notified_at
        ]
        selected.extend(new_jobs[:max_results])

    if len(selected) < min_results:
        for job in undelivered:
            if job.id in {j.id for j in selected}:
                continue
            selected.append(job)
            if len(selected) >= max_results:
                break

    return selected[:max_results]


def format_job_listing_line(job: JobPosting) -> str:
    location = format_location_display(
        location_text=job.location_text,
        city=job.city,
        country=job.country,
        is_remote=job.is_remote,
    )
    parts = [job.title or "Untitled", job.company_name or "Company not listed"]
    if location:
        parts.append(location)
    return " | ".join(parts)
