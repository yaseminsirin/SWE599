"""Controlled signal taxonomy and AI content validation for alert emails."""

from __future__ import annotations

import re

from apps.jobs.models import JobPosting

MIN_SIGNALS_TO_SHOW = 3

# Substrings that disqualify a signal or summary immediately.
_BANNED_SUBSTRINGS = (
    "position is",
    "located",
    "button below",
    "click on",
    "learn more",
    "applicants",
    "announcement",
    "agency button",
    "in support of",
    "admin operations",
    "analyst systems analyst",
    "management program",
    "share recurring themes",
    "search_mode",
    "semantic",
    "keyword mode",
)

_BANNED_SUMMARY_PHRASES = (
    "perfect match",
    "dream job",
    "guaranteed",
    "best job ever",
    "we found jobs that may interest you",
)

# Known technologies — allowed as one-word signals.
_TECHNOLOGY_WORDS = frozenset(
    {
        "sql",
        "python",
        "java",
        "javascript",
        "typescript",
        "react",
        "django",
        "flask",
        "fastapi",
        "aws",
        "azure",
        "gcp",
        "docker",
        "kubernetes",
        "postgres",
        "postgresql",
        "mysql",
        "mongodb",
        "redis",
        "kafka",
        "spark",
        "tableau",
        "excel",
        "git",
        "linux",
        "terraform",
        "devops",
        "qa",
        "graphql",
        "ml",
        "ai",
        "etl",
        "saas",
        "scrum",
        "agile",
        "kotlin",
        "golang",
        "rust",
        "snowflake",
        "databricks",
        "airflow",
        "ci/cd",
    }
)

# Role-agnostic professional concepts: (display label, match patterns).
SIGNAL_TAXONOMY: list[tuple[str, tuple[str, ...]]] = [
    ("Data analysis", ("data analysis", "data analyst", "analytical analysis", "analyze data")),
    ("Reporting", ("reporting", "report development", "analytical reporting", "status reports")),
    ("Business intelligence", ("business intelligence", "business analytics", "bi dashboard")),
    ("SQL", (" sql", "sql,", "sql.", "sql-based", "sql server", "mysql", "postgresql", "tsql")),
    ("Python", ("python",)),
    ("Dashboarding", ("dashboard", "dashboards", "dashboarding")),
    ("Performance metrics", ("performance metrics", "performance monitoring", "key performance")),
    ("Stakeholder communication", ("stakeholder", "stakeholders", "cross-functional communication")),
    ("Requirements analysis", ("requirements analysis", "requirements gathering", "business requirements")),
    ("API development", ("api development", "rest api", "restful api", "api design")),
    ("Backend services", ("backend service", "backend development", "backend engineer", "server-side")),
    ("Cloud infrastructure", ("cloud infrastructure", "cloud deployment", "cloud computing", " aws", " azure", " gcp")),
    ("DevOps", ("devops", "dev ops")),
    ("CI/CD", ("ci/cd", "continuous integration", "continuous delivery", "continuous deployment")),
    ("Testing and QA", ("quality assurance", "qa engineer", "test automation", "software testing", "testing and qa")),
    ("Product strategy", ("product strategy", "product vision", "product leadership")),
    ("Roadmap planning", ("roadmap planning", "product roadmap", "roadmap ownership")),
    ("User research", ("user research", "user interviews", "usability research")),
    ("Agile delivery", ("agile delivery", "agile development", "scrum", "kanban", "sprint planning")),
    ("Cybersecurity analysis", ("cybersecurity", "security analysis", "information security", "cyber security")),
    ("Financial analysis", ("financial analysis", "financial modeling", "financial reporting")),
    ("Operations analysis", ("operations analysis", "operational analysis", "business operations")),
    ("Program evaluation", ("program evaluation", "program analysis")),
    ("Process improvement", ("process improvement", "continuous improvement", "process optimization")),
    ("Distributed systems", ("distributed systems", "distributed system", "microservices")),
    ("Data-informed decision making", ("data-informed", "data driven", "data-driven", "decision support")),
]

_TOKEN_RE = re.compile(r"[a-z0-9+#./-]+", re.IGNORECASE)


def normalize_phrase(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _phrase_words(phrase: str) -> list[str]:
    return [w.lower() for w in _TOKEN_RE.findall(phrase or "")]


def _contains_banned(text: str) -> bool:
    lowered = (text or "").lower()
    return any(banned in lowered for banned in _BANNED_SUBSTRINGS)


def clean_ai_signal(raw: str) -> str | None:
    """Normalize and validate a single LLM or taxonomy signal."""
    phrase = normalize_phrase(raw)
    if not phrase or _contains_banned(phrase):
        return None
    if not is_quality_signal(phrase):
        return None
    return phrase


def is_quality_signal(phrase: str) -> bool:
    """
    Valid signals: 2-5 word professional phrases, or a known technology token.
    """
    cleaned = normalize_phrase(phrase)
    if not cleaned or _contains_banned(cleaned):
        return False

    words = _phrase_words(cleaned)
    if not words:
        return False

    if len(words) == 1:
        return words[0] in _TECHNOLOGY_WORDS

    if len(words) < 2 or len(words) > 5:
        return False

    return True


def filter_key_signals(signals: list[str], *, max_items: int = 5) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in signals:
        cleaned = clean_ai_signal(raw)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if len(result) >= max_items:
            break
    return result


def sanitize_ai_summary(text: str) -> str | None:
    """Return summary only when it passes quality checks."""
    cleaned = normalize_phrase(text)
    if not cleaned or len(cleaned) < 40:
        return None

    lowered = cleaned.lower()
    if _contains_banned(cleaned):
        return None
    if any(phrase in lowered for phrase in _BANNED_SUMMARY_PHRASES):
        return None
    if "share recurring themes" in lowered or "position is" in lowered:
        return None

    return cleaned


def is_quality_job_reason(reason: str) -> bool:
    """Validate a per-job LLM reason sentence."""
    cleaned = normalize_phrase(reason)
    if not cleaned or len(cleaned) < 30:
        return False
    if _contains_banned(cleaned):
        return False
    if not cleaned.endswith((".", "!", "?")):
        cleaned = cleaned + "."
    # Must look like a sentence (at least 6 words).
    if len(_phrase_words(cleaned)) < 6:
        return False
    return True


def _haystack_contains(haystack: str, pattern: str) -> bool:
    padded = f" {haystack.lower()} "
    return pattern.lower() in padded


def match_taxonomy_signals(haystack: str, *, max_signals: int = 5) -> list[str]:
    """Match controlled taxonomy labels against combined job/query text."""
    matched: list[str] = []
    seen: set[str] = set()
    for label, patterns in SIGNAL_TAXONOMY:
        if any(_haystack_contains(haystack, pattern) for pattern in patterns):
            key = label.lower()
            if key not in seen:
                seen.add(key)
                matched.append(label)
        if len(matched) >= max_signals:
            break
    return matched


def derive_taxonomy_signals(jobs: list[JobPosting], query: str = "", *, max_signals: int = 5) -> list[str]:
    """Taxonomy-based signals from query + job titles/descriptions."""
    parts = [query or ""]
    for job in jobs:
        parts.extend(
            filter(
                None,
                [
                    job.title or "",
                    job.normalized_title or "",
                    job.description_clean or "",
                    job.category_normalized or "",
                ],
            )
        )
    haystack = " ".join(parts)
    return match_taxonomy_signals(haystack, max_signals=max_signals)


def build_fallback_reason(job: JobPosting, query: str, signals: list[str] | None = None) -> str:
    """
    Professional template when LLM job_reason is unavailable.
    Never pastes random description fragments.
    """
    query = normalize_phrase(query) or "your alert"
    quality = filter_key_signals(signals or [])

    if len(quality) >= 2:
        return (
            f"This role matches your alert because its title and responsibilities are aligned with "
            f"{query}-related work, especially {quality[0].lower()} and {quality[1].lower()}."
        )

    return (
        "This role matches your alert based on similarity between the alert query "
        "and the job title/description."
    )


def build_fallback_summary(query: str) -> str:
    """Controlled non-LLM summary (shown only when explicitly enabled)."""
    query = normalize_phrase(query) or "your alert"
    return (
        f"These roles were selected because their titles and descriptions are semantically close "
        f"to your alert for {query}. The results are ranked using JobSense AI's matching pipeline."
    )


def signals_ready_for_display(signals: list[str]) -> bool:
    return len(filter_key_signals(signals)) >= MIN_SIGNALS_TO_SHOW


def build_jobs_haystack(jobs: list[JobPosting], query: str = "") -> str:
    parts = [query or ""]
    for job in jobs:
        parts.extend(
            filter(
                None,
                [job.title or "", job.normalized_title or "", job.description_clean or ""],
            )
        )
    return " ".join(parts)
