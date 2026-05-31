import re
from dataclasses import dataclass, field

from apps.jobs.models import JobPosting
from apps.jobs.services.job_labels import (
    employment_type_label,
    format_location_display,
    remote_label,
)

from ...models import JobAlert

_BANNED_PHRASES = (
    "perfect match",
    "dream job",
    "guaranteed",
    "best job ever",
)

_STOPWORDS = frozenset(
    {
        "and",
        "the",
        "for",
        "with",
        "you",
        "your",
        "our",
        "are",
        "was",
        "were",
        "will",
        "this",
        "that",
        "from",
        "have",
        "has",
        "job",
        "jobs",
        "role",
        "roles",
        "work",
        "team",
        "using",
        "use",
        "all",
        "any",
        "can",
        "may",
        "not",
        "but",
        "into",
        "over",
        "such",
        "their",
        "they",
        "them",
        "who",
        "what",
        "when",
        "where",
        "how",
        "about",
        "more",
        "other",
        "than",
        "then",
        "also",
        "able",
        "required",
        "requirements",
        "experience",
        "years",
        "year",
        "level",
        "senior",
        "junior",
        "mid",
        "full",
        "time",
        "based",
        "including",
        "within",
        "across",
        "through",
        "during",
        "while",
        "each",
        "both",
        "between",
        "well",
        "new",
        "one",
        "two",
        "three",
    }
)


@dataclass
class ParsedLlmEmail:
    summary: str = ""
    key_signals: list[str] = field(default_factory=list)
    job_notes: list[str] = field(default_factory=list)


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
            f"{index}. Title: {job.title or 'Untitled'}",
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


def parse_llm_response(raw: str) -> ParsedLlmEmail:
    text = (raw or "").strip()
    if not text:
        return ParsedLlmEmail()

    upper = text.upper()
    summary = ""
    key_signals: list[str] = []
    job_notes: list[str] = []

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

    for idx, (start, key) in enumerate(section_starts):
        end = section_starts[idx + 1][0] if idx + 1 < len(section_starts) else len(text)
        block = text[start + len(key) : end].strip()
        if key in {"KEY_SIGNALS:", "HIGHLIGHTS:"}:
            key_signals = _parse_bullets(block, max_items=5)
        elif key == "JOB_NOTES:":
            job_notes = _parse_numbered_notes(block)

    return ParsedLlmEmail(
        summary=summary,
        key_signals=key_signals,
        job_notes=job_notes,
    )


def derive_fallback_signals(jobs: list[JobPosting], *, max_signals: int = 4) -> list[str]:
    """Extract recurring themes from job text without hardcoded role rules."""
    counts: dict[str, int] = {}
    for job in jobs:
        haystack = " ".join(
            filter(
                None,
                [
                    job.title or "",
                    job.normalized_title or "",
                    job.description_clean or "",
                    job.category_normalized or "",
                ],
            )
        ).lower()
        for token in set(re.findall(r"[a-z0-9+#./-]{3,}", haystack)):
            if token in _STOPWORDS or token.isdigit():
                continue
            counts[token] = counts.get(token, 0) + 1

    ranked = sorted(counts.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
    signals: list[str] = []
    for token, count in ranked:
        if count < 2 and len(jobs) > 2:
            continue
        label = token.replace("-", " ").replace("/", " ").strip()
        signals.append(label.title())
        if len(signals) >= max_signals:
            break

    if not signals and jobs:
        title = (jobs[0].title or "matching roles").strip()
        signals.append(f"Roles similar to {title}")
    return signals[:max_signals]


def _sanitize_summary(text: str) -> str:
    cleaned = (text or "").strip()
    lowered = cleaned.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lowered:
            return ""
    banned_internal = ("search_mode", "semantic", "keyword mode", "additional filters")
    if any(term in lowered for term in banned_internal):
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
