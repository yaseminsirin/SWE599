import json
import re
from dataclasses import dataclass, field

from apps.jobs.models import JobPosting
from apps.jobs.services.job_labels import (
    employment_type_label,
    format_location_display,
    remote_label,
)

from ...models import JobAlert
from .content_helpers import (
    MIN_SIGNALS_TO_SHOW,
    build_fallback_reason,
    clean_ai_signal,
    derive_taxonomy_signals,
    filter_key_signals,
    is_quality_job_reason,
    normalize_phrase,
    sanitize_ai_summary,
    signals_ready_for_display,
)


@dataclass
class ParsedLlmEmail:
    summary: str = ""
    key_signals: list[str] = field(default_factory=list)
    job_notes: list[str] = field(default_factory=list)
    job_reasons: dict[str, str] = field(default_factory=dict)
    is_valid: bool = False


def get_alert_query_label(alert: JobAlert) -> str:
    return (alert.keyword or alert.name or "your alert").strip()


def build_llm_alert_context(alert: JobAlert) -> str:
    """Describe alert criteria for the LLM — no internal filter JSON."""
    parts: list[str] = []
    query = get_alert_query_label(alert)
    if query:
        parts.append(f"User search query: {query}")
    if alert.location_text:
        parts.append(f"Location preference: {alert.location_text}")
    if alert.is_remote is True:
        parts.append("Remote preference: remote-friendly roles")
    elif alert.is_remote is False:
        parts.append("Remote preference: on-site roles")
    if alert.employment_type:
        parts.append(f"Employment type: {employment_type_label(alert.employment_type)}")
    return "\n".join(parts) if parts else "General software/tech job alert"


def build_alert_query(alert: JobAlert) -> str:
    """Backward-compatible alias for LLM context."""
    return build_llm_alert_context(alert)


def format_user_alert_preferences(alert: JobAlert) -> list[str]:
    """Human-readable preferences for email display (no internal keys)."""
    prefs: list[str] = []
    if alert.location_text:
        prefs.append(f"Location: {alert.location_text}")
    if alert.is_remote is True:
        prefs.append("Remote only")
    elif alert.is_remote is False:
        prefs.append("On-site only")
    if alert.employment_type:
        prefs.append(f"Employment: {employment_type_label(alert.employment_type)}")
    return prefs


def format_jobs_for_context(jobs: list[JobPosting], *, max_jobs: int = 20) -> str:
    """Format retrieved jobs using only stored fields (no invented details)."""
    blocks: list[str] = []
    for index, job in enumerate(jobs[:max_jobs], start=1):
        location = format_location_display(
            location_text=job.location_text,
            city=job.city,
            country=job.country,
            is_remote=job.is_remote,
        )
        employment = employment_type_label(job.employment_type) if job.employment_type else ""
        summary = (job.description_clean or job.title or "").strip()
        if len(summary) > 320:
            summary = summary[:317].rstrip() + "..."

        lines = [
            f"{index}. job_id: {job.id}",
            f"   Title: {job.title or 'Untitled'}",
            f"   Company: {job.company_name or 'Not specified'}",
        ]
        if location:
            lines.append(f"   Location: {location}")
        lines.append(f"   Work style: {remote_label(is_remote=job.is_remote)}")
        if employment:
            lines.append(f"   Employment: {employment}")
        if job.source:
            lines.append(f"   Source: {job.source}")
        if summary:
            lines.append(f"   Summary: {summary}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def parse_llm_response(raw: str, jobs: list[JobPosting] | None = None) -> ParsedLlmEmail:
    """Parse and strictly validate LLM JSON output."""
    text = (raw or "").strip()
    if not text:
        return ParsedLlmEmail()

    payload_text = _extract_json_object(text)
    if not payload_text:
        return ParsedLlmEmail()

    try:
        data = json.loads(payload_text)
    except json.JSONDecodeError:
        return ParsedLlmEmail()

    return validate_llm_email_payload(data, jobs or [])


def validate_llm_email_payload(data: object, jobs: list[JobPosting]) -> ParsedLlmEmail:
    """Validate structured LLM JSON; reject low-quality fields."""
    if not isinstance(data, dict):
        return ParsedLlmEmail()

    summary_raw = data.get("summary")
    if not isinstance(summary_raw, str):
        return ParsedLlmEmail()

    summary = sanitize_ai_summary(summary_raw) or ""

    raw_signals = data.get("key_signals") or data.get("keySignals")
    key_signals: list[str] = []
    if isinstance(raw_signals, list):
        for item in raw_signals:
            if not isinstance(item, str):
                continue
            cleaned = clean_ai_signal(item)
            if cleaned:
                key_signals.append(cleaned)
    key_signals = filter_key_signals(key_signals)

    job_reasons: dict[str, str] = {}
    raw_reasons = data.get("job_reasons") or data.get("jobReasons")
    valid_ids = {str(job.id) for job in jobs}
    if isinstance(raw_reasons, dict):
        for job_id, reason in raw_reasons.items():
            key = str(job_id).strip()
            if key not in valid_ids or not isinstance(reason, str):
                continue
            cleaned = normalize_phrase(reason)
            if is_quality_job_reason(cleaned):
                job_reasons[key] = cleaned if cleaned.endswith((".", "!", "?")) else cleaned + "."

    has_summary = bool(summary)
    has_signals = signals_ready_for_display(key_signals)
    has_reasons = bool(job_reasons)
    is_valid = has_summary or has_signals or has_reasons

    return ParsedLlmEmail(
        summary=summary,
        key_signals=key_signals if has_signals else [],
        job_reasons=job_reasons,
        is_valid=is_valid,
    )


def build_job_match_notes(
    jobs: list[JobPosting],
    *,
    query: str,
    job_reasons: dict[str, str] | None = None,
    taxonomy_signals: list[str] | None = None,
) -> list[str]:
    """Resolve per-job match notes in job list order."""
    reasons = job_reasons or {}
    signals = taxonomy_signals or []
    result: list[str] = []
    for job in jobs:
        key = str(job.id)
        if key in reasons and is_quality_job_reason(reasons[key]):
            result.append(reasons[key])
        else:
            result.append(build_fallback_reason(job, query, signals))
    return result


def _extract_json_object(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start : end + 1]


__all__ = [
    "MIN_SIGNALS_TO_SHOW",
    "ParsedLlmEmail",
    "build_alert_query",
    "build_job_match_notes",
    "build_llm_alert_context",
    "derive_taxonomy_signals",
    "format_jobs_for_context",
    "format_user_alert_preferences",
    "get_alert_query_label",
    "parse_llm_response",
    "validate_llm_email_payload",
]
