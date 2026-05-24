from dataclasses import dataclass, field
import logging

from django.conf import settings

from apps.jobs.models import JobPosting

from ...models import JobAlert
from ..alert_retrieval import format_job_listing_line
from .job_context import (
    build_alert_query,
    format_jobs_for_context,
    parse_llm_response,
)
from .llm.factory import get_llm_provider
from .prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


@dataclass
class AlertEmailContent:
    explanation: str = ""
    job_bullets: list[str] = field(default_factory=list)
    used_rag: bool = False
    provider: str | None = None


def build_fallback_content(alert: JobAlert, jobs: list[JobPosting]) -> AlertEmailContent:
    criteria = build_alert_query(alert)
    query_hint = alert.keyword or "your saved criteria"
    explanation = (
        f"We found {len(jobs)} software/tech job(s) that may interest you based on "
        f'"{query_hint}". Review the listings below and apply directly on the source site.'
    )
    if criteria:
        explanation += f" Alert filters: {criteria.replace(chr(10), '; ')}."
    return AlertEmailContent(explanation=explanation, used_rag=False, provider=None)


def generate_alert_email_content(alert: JobAlert, jobs: list[JobPosting]) -> AlertEmailContent:
    """
    Generate RAG email copy from already-retrieved jobs.
    Never raises — falls back to plain content on any failure.
    """
    fallback = build_fallback_content(alert, jobs)
    if not jobs:
        return fallback

    try:
        provider = get_llm_provider()
    except ValueError as exc:
        logger.warning("Invalid LLM configuration: %s", exc)
        return fallback

    if provider is None or not provider.is_available():
        return fallback

    try:
        alert_query = build_alert_query(alert)
        jobs_context = format_jobs_for_context(jobs)
        user_prompt = build_user_prompt(
            alert_query=alert_query,
            jobs_context=jobs_context,
            job_count=len(jobs),
        )
        raw = provider.generate(system=SYSTEM_PROMPT, user=user_prompt)
        explanation, bullets = parse_llm_response(raw)
        if not explanation:
            return fallback
        return AlertEmailContent(
            explanation=explanation,
            job_bullets=bullets[:3],
            used_rag=True,
            provider=provider.provider_name,
        )
    except Exception as exc:
        logger.warning(
            "RAG email generation failed for alert %s: %s",
            alert.id,
            exc,
            exc_info=True,
        )
        return fallback


def build_alert_job_url(*, alert: JobAlert, job: JobPosting) -> str:
    base = getattr(settings, "SITE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/api/tracking/alert-click/{job.id}/?alert_id={alert.id}"


def compose_alert_email_body(
    content: AlertEmailContent,
    jobs: list[JobPosting],
    *,
    alert: JobAlert | None = None,
) -> str:
    lines: list[str] = []

    if content.explanation:
        lines.append(content.explanation)
        lines.append("")

    if content.job_bullets:
        lines.append("Highlights:")
        for bullet in content.job_bullets:
            lines.append(f"- {bullet}")
        lines.append("")

    lines.append("Matching jobs:")
    for job in jobs:
        listing = format_job_listing_line(job)
        if alert:
            apply_url = build_alert_job_url(alert=alert, job=job)
            lines.append(f"- {listing}")
            lines.append(f"  Apply: {apply_url}")
        else:
            lines.append(f"- {listing} | {job.job_url}")

    lines.append("")
    lines.append("— JobSense AI")
    return "\n".join(lines).strip() + "\n"
