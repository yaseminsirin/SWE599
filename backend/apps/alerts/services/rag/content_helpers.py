"""Testable helpers for alert email copy quality (signals, phrases, fallbacks)."""

from __future__ import annotations

import re
from collections import Counter

from apps.jobs.models import JobPosting

# Single-word tokens that must never appear alone as a Key Match Signal.
_MEANINGLESS_ALONE = frozenset(
    {
        "position",
        "located",
        "location",
        "office",
        "department",
        "company",
        "management",
        "program",
        "data",
        "business",
        "team",
        "analyst",
        "candidate",
        "employee",
        "organization",
        "government",
        "federal",
        "agency",
        "division",
        "directorate",
        "service",
        "services",
        "support",
        "general",
        "senior",
        "junior",
        "lead",
        "head",
        "chief",
        "director",
        "manager",
        "specialist",
        "coordinator",
        "assistant",
        "associate",
        "professional",
        "staff",
        "member",
        "unit",
        "section",
        "branch",
        "region",
        "state",
        "national",
        "public",
        "private",
        "sector",
        "industry",
        "client",
        "customer",
        "project",
        "projects",
    }
)

_LOCATION_WORDS = frozenset(
    {"located", "location", "office", "city", "state", "region", "remote", "onsite", "on-site"}
)

# Allowed one-word signals when they are real technologies/tools.
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
        "nodejs",
        "node",
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
        "powerbi",
        "excel",
        "git",
        "linux",
        "terraform",
        "ansible",
        "jenkins",
        "ci/cd",
        "graphql",
        "rest",
        "api",
        "apis",
        "ml",
        "ai",
        "nlp",
        "etl",
        "saas",
        "devops",
        "qa",
        "selenium",
        "jira",
        "figma",
        "scrum",
        "agile",
        "kotlin",
        "golang",
        "go",
        "rust",
        "c++",
        "c#",
        ".net",
        "spring",
        "hibernate",
        "snowflake",
        "databricks",
        "looker",
        "dbt",
        "airflow",
    }
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
        "had",
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
        "all",
        "any",
        "can",
        "may",
        "job",
        "jobs",
        "role",
        "roles",
        "new",
        "one",
        "two",
        "three",
        "each",
        "both",
        "between",
        "well",
        "full",
        "time",
        "part",
        "per",
        "via",
        "etc",
        "must",
        "should",
        "would",
        "could",
    }
)

LOW_CONFIDENCE_SIGNALS = [
    "Role-relevant responsibilities",
    "Skills aligned with your alert",
    "Similar job titles and descriptions",
]

_TOKEN_RE = re.compile(r"[a-z0-9+#./-]+", re.IGNORECASE)


def normalize_phrase(phrase: str) -> str:
    return " ".join((phrase or "").split()).strip()


def _phrase_words(phrase: str) -> list[str]:
    return [w.lower() for w in _TOKEN_RE.findall(phrase or "")]


def is_quality_signal(phrase: str) -> bool:
    """True when phrase is a meaningful 2+ word signal or a known technology."""
    cleaned = normalize_phrase(phrase)
    if not cleaned or len(cleaned) < 2:
        return False

    words = _phrase_words(cleaned)
    if not words:
        return False

    if len(words) == 1:
        token = words[0]
        if token in _MEANINGLESS_ALONE:
            return token in _TECHNOLOGY_WORDS
        return token in _TECHNOLOGY_WORDS or token not in _STOPWORDS

    if len(words) > 5:
        return False

    if all(w in _LOCATION_WORDS for w in words):
        return False

    if len(words) == 2 and all(w in _MEANINGLESS_ALONE for w in words):
        return False

    content_words = [w for w in words if w not in _STOPWORDS]
    return len(content_words) >= 2


def filter_key_signals(signals: list[str], *, max_items: int = 5) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in signals:
        phrase = normalize_phrase(raw)
        if not phrase:
            continue
        key = phrase.lower()
        if key in seen:
            continue
        if not is_quality_signal(phrase):
            continue
        seen.add(key)
        result.append(phrase)
        if len(result) >= max_items:
            break
    return result


def signals_are_confident(signals: list[str]) -> bool:
    return len(filter_key_signals(signals)) >= 2


def _tokenize_for_phrases(text: str) -> list[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text or "")]
    return [t for t in tokens if t not in _STOPWORDS and len(t) >= 2 and not t.isdigit()]


def extract_meaningful_phrases(
    text: str,
    *,
    query: str = "",
    min_words: int = 2,
    max_words: int = 4,
) -> list[str]:
    """Extract 2-4 word phrases from text, prioritizing query overlap."""
    tokens = _tokenize_for_phrases(text)
    if len(tokens) < min_words:
        return []

    query_tokens = set(_tokenize_for_phrases(query))
    phrases: list[tuple[int, str]] = []

    for n in range(min_words, max_words + 1):
        for i in range(len(tokens) - n + 1):
            chunk = tokens[i : i + n]
            if len(chunk) >= 2 and all(t in _MEANINGLESS_ALONE for t in chunk):
                continue
            phrase = " ".join(chunk)
            if not is_quality_signal(phrase):
                continue
            score = sum(1 for t in chunk if t in query_tokens)
            phrases.append((score, phrase))

    # Dedupe preserving best score
    best: dict[str, int] = {}
    for score, phrase in phrases:
        key = phrase.lower()
        best[key] = max(best.get(key, 0), score)

    ranked = sorted(best.items(), key=lambda item: (-item[1], -len(item[0].split()), item[0]))
    return [phrase for phrase, _score in ranked]


def derive_fallback_signals(
    jobs: list[JobPosting],
    query: str = "",
    *,
    max_signals: int = 4,
) -> list[str]:
    """Phrase-based fallback signals from job titles and descriptions."""
    phrase_counts: Counter[str] = Counter()
    query_phrases = extract_meaningful_phrases(query, query=query)

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
        )
        for phrase in extract_meaningful_phrases(haystack, query=query):
            phrase_counts[phrase.lower()] += 1

    # Boost query-aligned phrases appearing in corpus
    for phrase in query_phrases:
        key = phrase.lower()
        if key in phrase_counts:
            phrase_counts[key] += 2

    ranked = sorted(phrase_counts.items(), key=lambda item: (-item[1], -len(item[0].split()), item[0]))
    signals: list[str] = []
    for phrase_key, count in ranked:
        if count < 2 and len(jobs) > 2:
            continue
        display = " ".join(w.capitalize() if w.isalpha() else w for w in phrase_key.split())
        if is_quality_signal(display):
            signals.append(display)
        if len(signals) >= max_signals:
            break

    if not signals:
        for phrase in query_phrases[:max_signals]:
            if is_quality_signal(phrase):
                signals.append(phrase)

    return filter_key_signals(signals, max_items=max_signals)


def derive_fallback_job_reason(job: JobPosting, query: str) -> str:
    """Build a specific per-job match line from title + description phrases."""
    query = normalize_phrase(query) or "your alert"
    haystack = " ".join(
        filter(
            None,
            [
                job.title or "",
                job.description_clean or "",
            ],
        )
    )
    phrases = derive_fallback_signals([job], query=query, max_signals=3)
    if not phrases:
        phrases = extract_meaningful_phrases(haystack, query=query)[:3]

    if phrases:
        if len(phrases) == 1:
            focus = phrases[0].lower()
            return (
                f"This role fits your {query} alert because it emphasizes {focus} "
                f"in the listed responsibilities at {job.company_name or 'this organization'}."
            )
        joined = ", ".join(phrases[:-1]) + f", and {phrases[-1]}"
        return (
            f"This role fits your {query} alert because it focuses on {joined.lower()} "
            f"based on the title and description."
        )

    title = job.title or "This position"
    return (
        f"This role fits your {query} alert through its title ({title}) "
        f"and responsibilities described for {job.company_name or 'the employer'}."
    )


def derive_fallback_summary(alert_query: str, jobs: list[JobPosting], signals: list[str]) -> str:
    """Query-aware summary without generic filler."""
    query = normalize_phrase(alert_query) or "your alert"
    count = len(jobs)
    noun = "role" if count == 1 else "roles"

    quality_signals = filter_key_signals(signals)
    if quality_signals:
        themes = ", ".join(s.lower() for s in quality_signals[:3])
        return (
            f"These {noun} align with your {query} alert because they emphasize "
            f"{themes} across the matched listings."
        )

    return (
        f"These {noun} align with your {query} alert based on recurring responsibilities, "
        f"skills, and job titles found in your matched results."
    )


def resolve_key_signals_for_email(signals: list[str]) -> tuple[list[str], bool]:
    """
    Return (signals_to_display, show_section).
    Uses low-confidence generic bullets when filtered signals are insufficient.
    """
    quality = filter_key_signals(signals)
    if len(quality) >= 2:
        return quality, True
    if len(quality) == 1:
        return quality + LOW_CONFIDENCE_SIGNALS[:2], True
    return LOW_CONFIDENCE_SIGNALS, True
