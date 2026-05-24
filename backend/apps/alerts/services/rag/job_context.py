import json

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


def build_alert_query(alert: JobAlert) -> str:
    """Describe alert criteria for the LLM (retrieval already done)."""
    parts: list[str] = []
    if alert.name:
        parts.append(f"Alert name: {alert.name}")
    if alert.keyword:
        parts.append(f"Search query: {alert.keyword}")
    if alert.location_text:
        parts.append(f"Location preference: {alert.location_text}")
    if alert.is_remote is True:
        parts.append("Remote preference: remote-friendly roles")
    elif alert.is_remote is False:
        parts.append("Remote preference: on-site roles")
    if alert.employment_type:
        parts.append(f"Employment type: {alert.employment_type}")
    if alert.filters:
        parts.append(f"Additional filters: {json.dumps(alert.filters, ensure_ascii=False)}")
    return "\n".join(parts) if parts else "General software/tech job alert"


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
        if len(summary) > 240:
            summary = summary[:237].rstrip() + "..."

        lines = [
            f"{index}. Title: {job.title or 'Untitled'}",
            f"   Company: {job.company_name or 'Not specified'}",
        ]
        if location:
            lines.append(f"   Location: {location}")
        lines.append(f"   Work style: {remote_label(is_remote=job.is_remote)}")
        if employment:
            lines.append(f"   Employment: {employment}")
        if summary:
            lines.append(f"   Summary: {summary}")
        if job.job_url:
            lines.append(f"   URL: {job.job_url}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def parse_llm_response(raw: str) -> tuple[str, list[str]]:
    text = (raw or "").strip()
    if not text:
        return "", []

    upper = text.upper()
    if "EXPLANATION:" not in upper:
        return _sanitize_explanation(text[:600]), []

    expl_idx = upper.index("EXPLANATION:")
    highlights_idx = upper.find("HIGHLIGHTS:")
    bullets_idx = upper.find("JOB_BULLETS:")
    section_idx = highlights_idx if highlights_idx != -1 else bullets_idx

    if section_idx == -1:
        explanation = text[expl_idx + len("EXPLANATION:") :].strip()
        return _sanitize_explanation(explanation), []

    label_len = len("HIGHLIGHTS:") if highlights_idx != -1 else len("JOB_BULLETS:")
    explanation = text[expl_idx + len("EXPLANATION:") : section_idx].strip()
    bullet_block = text[section_idx + label_len :].strip()
    bullets = _parse_bullets(bullet_block)
    return _sanitize_explanation(explanation), bullets


def _sanitize_explanation(text: str) -> str:
    cleaned = (text or "").strip()
    lowered = cleaned.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lowered:
            return ""
    return cleaned


def _parse_bullets(block: str) -> list[str]:
    bullets: list[str] = []
    for line in block.splitlines():
        cleaned = line.strip().lstrip("-•*").strip()
        if cleaned:
            bullets.append(cleaned)
    return bullets[:3]
