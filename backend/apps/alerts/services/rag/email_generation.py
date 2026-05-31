from dataclasses import dataclass, field
import logging

from django.conf import settings

from apps.jobs.models import JobPosting
from apps.jobs.services.job_urls import resolve_external_job_url

from ...models import JobAlert
from .content_helpers import derive_taxonomy_signals, signals_ready_for_display
from .job_context import (
    build_job_match_notes,
    build_llm_alert_context,
    format_jobs_for_context,
    get_alert_query_label,
    parse_llm_response,
)
from .llm.factory import get_llm_provider
from .prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


@dataclass
class AlertEmailContent:
    summary: str = ""
    key_signals: list[str] = field(default_factory=list)
    job_match_notes: list[str] = field(default_factory=list)
    show_summary: bool = False
    show_key_signals: bool = False
    used_rag: bool = False
    provider: str | None = None

    @property
    def explanation(self) -> str:
        return self.summary

    @property
    def job_bullets(self) -> list[str]:
        return self.key_signals


def build_alert_subject(alert: JobAlert, job_count: int) -> str:
    query = get_alert_query_label(alert)
    noun = "match" if job_count == 1 else "matches"
    return f"JobSense AI Alert: {query} — {job_count} relevant {noun}"


def build_fallback_content(alert: JobAlert, jobs: list[JobPosting]) -> AlertEmailContent:
    """No LLM — hide AI Insight; show taxonomy signals only when >= 3 matches."""
    query = get_alert_query_label(alert)
    taxonomy = derive_taxonomy_signals(jobs, query=query)
    show_signals = signals_ready_for_display(taxonomy)
    job_notes = build_job_match_notes(jobs, query=query, taxonomy_signals=taxonomy)

    return AlertEmailContent(
        summary="",
        key_signals=taxonomy if show_signals else [],
        job_match_notes=job_notes,
        show_summary=False,
        show_key_signals=show_signals,
        used_rag=False,
        provider=None,
    )


def generate_alert_email_content(alert: JobAlert, jobs: list[JobPosting]) -> AlertEmailContent:
    """
    Generate RAG email copy from already-retrieved jobs.
    Never raises — falls back to taxonomy-only content on any failure.
    """
    fallback = build_fallback_content(alert, jobs)
    if not jobs:
        return fallback

    query = get_alert_query_label(alert)
    taxonomy = derive_taxonomy_signals(jobs, query=query)

    try:
        provider = get_llm_provider()
    except ValueError as exc:
        logger.warning("Invalid LLM configuration: %s", exc)
        return fallback

    if provider is None or not provider.is_available():
        return fallback

    try:
        alert_query = build_llm_alert_context(alert)
        jobs_context = format_jobs_for_context(jobs)
        user_prompt = build_user_prompt(
            alert_query=alert_query,
            jobs_context=jobs_context,
            job_count=len(jobs),
        )
        raw = provider.generate(system=SYSTEM_PROMPT, user=user_prompt)
        parsed = parse_llm_response(raw, jobs=jobs)

        if not parsed.is_valid:
            return fallback

        show_summary = bool(parsed.summary)
        show_signals = signals_ready_for_display(parsed.key_signals)
        job_notes = build_job_match_notes(
            jobs,
            query=query,
            job_reasons=parsed.job_reasons,
            taxonomy_signals=taxonomy,
        )

        return AlertEmailContent(
            summary=parsed.summary if show_summary else "",
            key_signals=parsed.key_signals if show_signals else [],
            job_match_notes=job_notes,
            show_summary=show_summary,
            show_key_signals=show_signals,
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


def build_alert_apply_url(*, alert: JobAlert, job: JobPosting) -> str:
    """
    Link for View job in alert emails.

    Prefer the original HTTPS listing URL — Gmail and other clients often block or
    mishandle http://IP:8000 tracking redirects. Fall back to site search when
    the stored listing URL is missing or a demo placeholder.
    """
    direct = resolve_external_job_url(job.job_url)
    if direct:
        return direct
    base = getattr(settings, "SITE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/search/"


def compose_alert_email(
    content: AlertEmailContent,
    jobs: list[JobPosting],
    *,
    alert: JobAlert,
) -> tuple[str, str]:
    """Return (plain_text, html) email bodies."""
    from .email_html import compose_alert_email_html, compose_alert_email_text

    text_body = compose_alert_email_text(content, jobs, alert=alert)
    html_body = compose_alert_email_html(content, jobs, alert=alert)
    return text_body, html_body


def compose_alert_email_body(
    content: AlertEmailContent,
    jobs: list[JobPosting],
    *,
    alert: JobAlert | None = None,
) -> str:
    """Backward-compatible plain-text composer."""
    if alert is None:
        raise ValueError("alert is required")
    text_body, _ = compose_alert_email(content, jobs, alert=alert)
    return text_body
