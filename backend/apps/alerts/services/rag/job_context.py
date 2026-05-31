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
    derive_fallback_job_reason,
    derive_fallback_signals,
    derive_fallback_summary,
    filter_key_signals,
    normalize_phrase,
    resolve_key_signals_for_email,
)

_BANNED_PHRASES = (
    "perfect match",
    "dream job",
    "guaranteed",
    "best job ever",
)

_GENERIC_SUMMARY_PATTERNS = (
    "share recurring themes across title",
    "we found jobs that may interest you",
    "these listings share recurring themes",
)


@dataclass
class ParsedLlmEmail:
    summary: str = ""
    key_signals: list[str] = field(default_factory=list)
    job_notes: list[str] = field(default_factory=list)
    job_reasons: dict[str, str] = field(default_factory=dict)


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
    text = (raw or "").strip()
    if not text:
        return ParsedLlmEmail()

    json_parsed = _parse_llm_json(text, jobs or [])
    if json_parsed.summary or json_parsed.key_signals or json_parsed.job_reasons:
        return json_parsed

    return _parse_legacy_sections(text)


def build_job_match_notes(
    jobs: list[JobPosting],
    *,
    query: str,
    job_reasons: dict[str, str] | None = None,
    ordered_notes: list[str] | None = None,
) -> list[str]:
    """Resolve per-job match notes in job list order."""
    reasons = job_reasons or {}
    notes = ordered_notes or []
    result: list[str] = []
    for index, job in enumerate(jobs):
        key = str(job.id)
        if key in reasons and normalize_phrase(reasons[key]):
            result.append(normalize_phrase(reasons[key]))
        elif index < len(notes) and normalize_phrase(notes[index]):
            result.append(normalize_phrase(notes[index]))
        else:
            result.append(derive_fallback_job_reason(job, query))
    return result


def _parse_llm_json(raw: str, jobs: list[JobPosting]) -> ParsedLlmEmail:
    payload_text = _extract_json_object(raw)
    if not payload_text:
        return ParsedLlmEmail()

    try:
        data = json.loads(payload_text)
    except json.JSONDecodeError:
        return ParsedLlmEmail()

    if not isinstance(data, dict):
        return ParsedLlmEmail()

    summary = _sanitize_summary(str(data.get("summary") or ""))
    raw_signals = data.get("key_signals") or data.get("keySignals") or []
    key_signals = filter_key_signals(
        [str(item) for item in raw_signals] if isinstance(raw_signals, list) else []
    )

    job_reasons: dict[str, str] = {}
    raw_reasons = data.get("job_reasons") or data.get("jobReasons") or {}
    if isinstance(raw_reasons, dict):
        valid_ids = {str(job.id) for job in jobs}
        for job_id, reason in raw_reasons.items():
            key = str(job_id).strip()
            if key in valid_ids:
                cleaned = normalize_phrase(str(reason or ""))
                if cleaned and not _is_generic_job_reason(cleaned):
                    job_reasons[key] = cleaned

    ordered_notes: list[str] = []
    if not job_reasons and jobs:
        for job in jobs:
            key = str(job.id)
            if isinstance(raw_reasons, dict) and key in raw_reasons:
                ordered_notes.append(normalize_phrase(str(raw_reasons[key])))

    return ParsedLlmEmail(
        summary=summary,
        key_signals=key_signals,
        job_notes=ordered_notes,
        job_reasons=job_reasons,
    )


def _parse_legacy_sections(text: str) -> ParsedLlmEmail:
    upper = text.upper()
    summary_key = "SUMMARY:" if "SUMMARY:" in upper else "EXPLANATION:"
    signals_key = "KEY_SIGNALS:" if "KEY_SIGNALS:" in upper else None
    if signals_key is None and "HIGHLIGHTS:" in upper:
        signals_key = "HIGHLIGHTS:"
    notes_key = "JOB_NOTES:" if "JOB_NOTES:" in upper else None

    if summary_key not in upper:
        return ParsedLlmEmail(summary=_sanitize_summary(text[:800]))

    summary_start = upper.index(summary_key) + len(summary_key)
    section_starts = []
    for key in (signals_key, notes_key):
        if key and key in upper:
            section_starts.append((upper.index(key), key))

    section_starts.sort()
    first_section = section_starts[0][0] if section_starts else len(text)
    summary = _sanitize_summary(text[summary_start:first_section].strip())

    key_signals: list[str] = []
    job_notes: list[str] = []
    for idx, (start, key) in enumerate(section_starts):
        end = section_starts[idx + 1][0] if idx + 1 < len(section_starts) else len(text)
        block = text[start + len(key) : end].strip()
        if key in {"KEY_SIGNALS:", "HIGHLIGHTS:"}:
            key_signals = filter_key_signals(_parse_bullets(block, max_items=8))
        elif key == "JOB_NOTES:":
            job_notes = _parse_numbered_notes(block)

    return ParsedLlmEmail(
        summary=summary,
        key_signals=key_signals,
        job_notes=job_notes,
    )


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


def _is_generic_job_reason(reason: str) -> bool:
    lowered = reason.lower()
    generic_markers = (
        "related to your",
        "through the title and listed responsibilities",
        "through the title and responsibilities",
    )
    return any(marker in lowered for marker in generic_markers)


def _sanitize_summary(text: str) -> str:
    cleaned = normalize_phrase(text)
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lowered:
            return ""
    banned_internal = ("search_mode", "semantic", "keyword mode", "additional filters")
    if any(term in lowered for term in banned_internal):
        return ""
    for pattern in _GENERIC_SUMMARY_PATTERNS:
        if pattern in lowered:
            return ""
    return cleaned


def _parse_bullets(block: str, *, max_items: int) -> list[str]:
    bullets: list[str] = []
    for line in block.splitlines():
        cleaned = line.strip().lstrip("-•*").strip()
        if cleaned:
            bullets.append(cleaned)
    return bullets[:max_items]


def _parse_numbered_notes(block: str) -> list[str]:
    notes: list[str] = []
    for line in block.splitlines():
        cleaned = re.sub(r"^\s*\d+[\).\:-]\s*", "", line.strip())
        if cleaned:
            notes.append(cleaned)
    return notes


# Re-export for backward compatibility
__all__ = [
    "ParsedLlmEmail",
    "build_alert_query",
    "build_job_match_notes",
    "build_llm_alert_context",
    "derive_fallback_signals",
    "derive_fallback_summary",
    "format_jobs_for_context",
    "format_user_alert_preferences",
    "get_alert_query_label",
    "parse_llm_response",
    "resolve_key_signals_for_email",
]
