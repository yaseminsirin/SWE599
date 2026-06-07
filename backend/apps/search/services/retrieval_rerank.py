"""Lightweight lexical reranking on top of pgvector semantic candidates."""

from __future__ import annotations

import logging
import re
from typing import Any

from django.conf import settings

from apps.jobs.models import JobPosting

from .job_quality import _tokenize

logger = logging.getLogger(__name__)

NATURAL_LANGUAGE_PHRASES = (
    "i enjoy",
    "i want",
    "i have experience",
    "working with",
    "looking for",
)

# Vocabulary tokens matched from NL queries (after plural normalization).
SKILL_VOCABULARY = frozenset(
    {
        "backend",
        "developer",
        "software",
        "engineer",
        "api",
        "database",
        "scalable",
        "cloud",
        "microservices",
        "python",
        "data",
        "analytics",
        "dashboard",
        "sql",
        "business",
        "insights",
        "reporting",
        "analyst",
        "devops",
        "frontend",
        "fullstack",
        "java",
        "javascript",
        "typescript",
        "react",
        "django",
        "kubernetes",
        "aws",
    }
)

PLURAL_NORMALIZE = {
    "apis": "api",
    "databases": "database",
    "applications": "application",
    "dashboards": "dashboard",
}

# Implicit role terms when NL queries describe building/designing systems but omit "developer".
NL_SKILL_EXPANSIONS = {
    "backend": {"developer", "software", "engineer"},
    "api": {"developer", "software"},
    "database": {"engineer", "developer"},
}

# Terms used to order compact retrieval text for embeddings.
RETRIEVAL_TERM_PRIORITY = (
    "backend",
    "developer",
    "software",
    "engineer",
    "api",
    "database",
    "scalable",
    "cloud",
    "microservices",
    "python",
    "data",
    "analytics",
    "dashboard",
    "sql",
    "business",
    "insights",
    "analyst",
    "reporting",
    "devops",
    "frontend",
)

ANALYST_SKILL_SIGNALS = frozenset(
    {"analyst", "analytics", "dashboard", "insights", "reporting", "business"}
)

SINGLE_TERM_BODY_SEMANTIC_MIN = 0.20

SEARCH_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "for",
        "with",
        "to",
        "in",
        "on",
        "at",
        "of",
        "is",
        "are",
        "be",
        "as",
        "by",
        "from",
        "that",
        "this",
        "i",
        "am",
        "looking",
        "role",
        "roles",
        "job",
        "jobs",
        "work",
        "experience",
        "experienced",
        "building",
        "modern",
        "teams",
        "team",
        "services",
        "service",
        "applications",
        "application",
        "driven",
        "based",
        "using",
        "use",
        "new",
        "our",
        "your",
        "you",
        "we",
        "will",
        "can",
        "have",
        "has",
        "who",
        "what",
        "when",
        "where",
        "how",
        "all",
        "any",
        "per",
        "via",
        "into",
        "over",
        "under",
        "about",
        "than",
        "then",
        "them",
        "they",
        "their",
        "there",
        "these",
        "those",
        "not",
        "but",
        "also",
        "etc",
        "etc.",
    }
)


TECH_QUERY_SIGNALS = frozenset(
    {
        "dev",
        "python",
        "django",
        "flask",
        "react",
        "java",
        "javascript",
        "typescript",
        "developer",
        "engineer",
        "software",
        "backend",
        "frontend",
        "devops",
        "data",
        "sql",
        "api",
        "apis",
        "cloud",
        "fullstack",
        "mobile",
        "ios",
        "android",
        "ml",
        "ai",
        "kubernetes",
        "aws",
    }
)

# Too broad for SQL prefilter / title gate — match unrelated clerk & healthcare listings.
GENERIC_BROAD_TERMS = frozenset({"data", "web", "api", "apis", "cloud", "mobile", "ai", "ml", "sql"})

SHORT_QUERY_EXPANSIONS = {
    "dev": {"developer", "devops", "software", "engineer"},
}

STRONG_ROLE_TERMS = frozenset(
    {
        "python",
        "django",
        "flask",
        "react",
        "java",
        "javascript",
        "typescript",
        "developer",
        "engineer",
        "software",
        "backend",
        "frontend",
        "devops",
        "programmer",
        "fullstack",
        "kubernetes",
        "aws",
        "analyst",
        "scientist",
    }
)

# Role nouns that alone are too broad when paired with a specific skill (e.g. backend + engineer).
GENERIC_ROLE_TERMS = frozenset(
    {
        "engineer",
        "developer",
        "programmer",
        "analyst",
        "scientist",
        "architect",
        "software",
    }
)

IT_CATEGORY_HINTS = (
    "information technology",
    "software",
    "computer",
    "engineering",
    "developer",
    "programmer",
    "data science",
    "cyber",
)

SOFTWARE_CATEGORY_HINTS = (
    "information technology",
    "software",
    "computer",
    "developer",
    "programmer",
    "data science",
    "cyber",
)

NON_TECH_JOB_PHRASES = (
    "truck driver",
    "cdl",
    "owner operator",
    "delivery driver",
    "flatbed",
    "logistics",
    "warehouse",
    "security officer",
    "forklift",
    "janitor",
    "cashier",
    "nurse aide",
    "psychiatrist",
    "program support assistant",
    "miscellaneous clerk",
    "healthcare",
    "registered nurse",
    "medical assistant",
)

NON_TECH_TITLE_TOKENS = frozenset(
    {
        "physicist",
        "physics",
        "nurse",
        "nursing",
        "physician",
        "psychiatrist",
        "psychologist",
        "therapist",
        "custodian",
        "janitor",
        "cashier",
        "driver",
        "truck",
        "warehouse",
        "forklift",
        "clerk",
        "aide",
        "surgeon",
        "dentist",
        "veterinarian",
        "paramedic",
        "ast",
    }
)

NON_TECH_CATEGORY_HINTS = (
    "physics",
    "healthcare",
    "medical",
    "nursing",
    "transportation",
    "logistics",
    "retail",
    "hospitality",
    "construction",
    "agriculture",
    "biology",
    "chemistry",
)

SOFTWARE_TITLE_TOKENS = frozenset(
    {
        "software",
        "computer",
        "developer",
        "programmer",
        "fullstack",
        "devops",
        "cloud",
        "cyber",
        "cybersecurity",
        "web",
        "mobile",
        "react",
        "python",
        "java",
        "typescript",
        "javascript",
        "data",
        "saas",
        "platform",
        "stack",
        "technical",
        "programming",
        "backend",
        "frontend",
    }
)

NON_SOFTWARE_ENGINEER_TITLE_TOKENS = frozenset(
    {
        "mechanical",
        "healthcare",
        "aerospace",
        "structural",
        "civil",
        "materials",
        "safety",
        "fire",
        "electronics",
        "electrical",
        "interdisciplinary",
        "physicist",
        "facilities",
        "network",
        "environmental",
        "chemical",
        "biomedical",
        "manufacturing",
    }
)


def content_tokens(text: str) -> set[str]:
    return {token for token in _tokenize(text) if len(token) >= 3 and token not in SEARCH_STOPWORDS}


def normalize_skill_token(token: str) -> str:
    return PLURAL_NORMALIZE.get(token, token)


def is_natural_language_query(query: str) -> bool:
    stripped = (query or "").strip().lower()
    if not stripped:
        return False
    if len(stripped.split()) > 6:
        return True
    return any(phrase in stripped for phrase in NATURAL_LANGUAGE_PHRASES)


def extract_skill_terms(query: str, *, include_nl_expansions: bool = True) -> set[str]:
    """Pull searchable skill/role terms from NL or keyword queries."""
    terms: set[str] = set()
    raw_tokens = set(_tokenize(query))
    for token in raw_tokens:
        if len(token) < 3:
            continue
        normalized = normalize_skill_token(token)
        if normalized in SKILL_VOCABULARY:
            terms.add(normalized)
        elif token in SKILL_VOCABULARY:
            terms.add(token)
    if "analyzing" in raw_tokens or "analysis" in raw_tokens:
        terms.add("analytics")
    if include_nl_expansions:
        for anchor, extras in NL_SKILL_EXPANSIONS.items():
            if anchor in terms:
                terms.update(extras)
    if terms & ANALYST_SKILL_SIGNALS:
        return terms
    if terms & STRONG_ROLE_TERMS:
        terms -= {"data", "web"}
    else:
        terms -= GENERIC_BROAD_TERMS
    return terms


def _order_retrieval_terms(terms: set[str]) -> str:
    ordered: list[str] = []
    for term in RETRIEVAL_TERM_PRIORITY:
        if term in terms:
            ordered.append(term)
    for term in sorted(terms):
        if term not in ordered:
            ordered.append(term)
    return " ".join(ordered)


def is_tech_query(query: str) -> bool:
    return bool(content_tokens(query) & TECH_QUERY_SIGNALS)


def prefilter_terms(query: str) -> set[str]:
    """Terms used to narrow pgvector for short keyword queries."""
    if is_natural_language_query(query):
        skills = extract_skill_terms(query, include_nl_expansions=False)
        if skills:
            return skills
    terms = core_query_terms(query) or content_tokens(query)
    if not terms:
        return set()
    for token in content_tokens(query):
        terms.update(SHORT_QUERY_EXPANSIONS.get(token, set()))
    if is_tech_query(query):
        strong = terms & STRONG_ROLE_TERMS
        if strong:
            return strong
    specific = terms - GENERIC_BROAD_TERMS
    return specific if specific else terms


def should_skip_pgvector_prefilter(query: str) -> bool:
    """NL queries search the full embedded corpus; short queries may narrow first."""
    return is_natural_language_query(query)


def match_terms_for_relevance(query: str) -> set[str]:
    if is_natural_language_query(query):
        skills = extract_skill_terms(query)
        if skills:
            return skills
    terms = core_query_terms(query) or content_tokens(query)
    for token in content_tokens(query):
        terms.update(SHORT_QUERY_EXPANSIONS.get(token, set()))
    if is_tech_query(query):
        strong = terms & STRONG_ROLE_TERMS
        if strong:
            return strong
    return terms


def _prefix_overlap(query_terms: set[str], doc_terms: set[str]) -> bool:
    """Allow short query prefixes like 'dev' to match 'developer'."""
    if not query_terms or not doc_terms:
        return False
    for q in query_terms:
        if len(q) < 3:
            continue
        if len(q) <= 4 and any(term.startswith(q) for term in doc_terms):
            return True
    return False


def core_query_terms(query: str, *, max_terms: int = 6) -> set[str]:
    """Focus lexical/relevance checks on the most specific query terms."""
    terms = content_tokens(query)
    if not terms:
        return set()
    if len(terms) <= max_terms:
        return terms
    return set(sorted(terms, key=lambda token: (-len(token), token))[:max_terms])


def retrieval_query_text(query: str) -> str:
    """
    Compact text for embedding / pgvector retrieval.

    Short tech queries keep the user's phrasing ('backend engineer') so vectors align
    with job titles. Long NL queries compress to ordered skill terms.
    """
    stripped = (query or "").strip()
    if not stripped:
        return ""
    if is_natural_language_query(stripped):
        skills = extract_skill_terms(stripped)
        if skills:
            return _order_retrieval_terms(skills)

    word_count = len(stripped.split())
    if word_count <= 4 and is_tech_query(stripped):
        return stripped

    strong = prefilter_terms(stripped)
    if strong and not is_natural_language_query(stripped):
        return _order_retrieval_terms(strong)
    terms = core_query_terms(stripped)
    if word_count > 5 and terms:
        return _order_retrieval_terms(terms - GENERIC_BROAD_TERMS or terms)
    if len(terms) >= 2:
        return _order_retrieval_terms(terms)
    return stripped


def _job_text_blob(job: JobPosting) -> str:
    return " ".join(
        filter(
            None,
            [
                job.title,
                job.normalized_title,
                job.category_normalized,
                job.category_raw,
                (job.description_clean or "")[:500],
            ],
        )
    ).lower()


def _job_category_blob(job: JobPosting) -> str:
    return " ".join(
        filter(None, [job.category_normalized, job.category_raw])
    ).lower()


def is_software_tech_job(job: JobPosting) -> bool:
    if is_non_software_engineer_title(job) or is_non_tech_job(job):
        return False

    title_tokens = content_tokens(
        " ".join(filter(None, [job.title, job.normalized_title]))
    )
    if title_tokens & SOFTWARE_TITLE_TOKENS:
        return True

    category_blob = _job_category_blob(job)
    if any(hint in category_blob for hint in SOFTWARE_CATEGORY_HINTS):
        return True

    return bool(content_tokens(_job_text_blob(job)) & SOFTWARE_TITLE_TOKENS)


def is_non_software_engineer_title(job: JobPosting) -> bool:
    title_tokens = content_tokens(
        " ".join(filter(None, [job.title, job.normalized_title]))
    )
    if not title_tokens & {"engineer", "developer"}:
        return False
    return bool(title_tokens & NON_SOFTWARE_ENGINEER_TITLE_TOKENS)


def is_non_tech_job(job: JobPosting) -> bool:
    """Obvious non-software roles (e.g. physicist, nurse) even if the body mentions engineering."""
    title_tokens = content_tokens(
        " ".join(filter(None, [job.title, job.normalized_title]))
    )
    if title_tokens & NON_TECH_TITLE_TOKENS:
        return True

    category_blob = _job_category_blob(job)
    if any(hint in category_blob for hint in NON_TECH_CATEGORY_HINTS):
        return True

    blob = _job_text_blob(job)
    return any(phrase in blob for phrase in NON_TECH_JOB_PHRASES)


def _term_in_text(term: str, text: str) -> bool:
    return bool(re.search(rf"\b{re.escape(term)}\b", text or "", flags=re.IGNORECASE))


def has_meaningful_stack_signal(job: JobPosting, specific_terms: set[str]) -> bool:
    """
    Specific stack terms (e.g. backend) must appear in the title or in an IT-category body —
    not as an incidental mention in a physics/medical posting.
    """
    if not specific_terms:
        return True

    title_tokens = content_tokens(
        " ".join(filter(None, [job.title, job.normalized_title]))
    )
    if specific_terms & title_tokens:
        return True

    category_blob = _job_category_blob(job)
    if not any(hint in category_blob for hint in IT_CATEGORY_HINTS):
        return False

    body = (job.description_clean or "").lower()
    return any(_term_in_text(term, body) for term in specific_terms)


def specific_query_terms(q_terms: set[str]) -> set[str]:
    """Skill/stack terms that must appear on a job when present in the query."""
    return q_terms - GENERIC_ROLE_TERMS - GENERIC_BROAD_TERMS


def is_misleading_engineer_listing(job: JobPosting, specific_terms: set[str]) -> bool:
    """
    Drop staff/product engineer titles when the query targets a specific stack (e.g. backend).

    Unlike a hard 'backend must exist' rule, this only blocks obvious false positives so
    legitimate software roles with backend mentioned in the body can still match.
    """
    if not specific_terms:
        return False

    title_tokens = content_tokens(" ".join(filter(None, [job.title, job.normalized_title])))
    if specific_terms & title_tokens:
        return False

    searchable = content_tokens(_job_text_blob(job))
    if specific_terms & searchable:
        return False

    if not title_tokens & {"engineer", "developer", "programmer"}:
        return False

    if "staff" in title_tokens or "product" in title_tokens:
        return True

    category_blob = " ".join(
        filter(None, [job.category_normalized, job.category_raw])
    ).lower()
    if "product" in category_blob and "engineer" in title_tokens:
        return True

    return False


def is_domain_mismatch(query: str, job: JobPosting) -> bool:
    """Drop obvious cross-domain neighbors (e.g. truck driver for a Python query)."""
    q_terms = content_tokens(query)
    if not q_terms & TECH_QUERY_SIGNALS:
        return False

    if is_non_tech_job(job):
        return True

    blob = _job_text_blob(job)
    job_terms = content_tokens(blob)
    if job_terms & TECH_QUERY_SIGNALS:
        return False

    return any(phrase in blob for phrase in NON_TECH_JOB_PHRASES)


def compute_lexical_score(query: str, job: JobPosting) -> float:
    q_tokens = core_query_terms(query)
    if not q_tokens:
        q_tokens = content_tokens(query)
    if not q_tokens:
        return 0.0

    title_tokens = content_tokens(job.title or "")
    norm_title_tokens = content_tokens(job.normalized_title or "")
    body_tokens = content_tokens(job.description_clean or "")
    category_tokens = content_tokens(
        " ".join(filter(None, [job.category_normalized, job.category_raw]))
    )

    title_overlap = len(q_tokens.intersection(title_tokens)) / len(q_tokens)
    norm_overlap = len(q_tokens.intersection(norm_title_tokens)) / len(q_tokens)
    body_overlap = len(q_tokens.intersection(body_tokens)) / len(q_tokens)
    category_overlap = len(q_tokens.intersection(category_tokens)) / len(q_tokens)

    score = min(
        1.0,
        (0.50 * title_overlap)
        + (0.25 * norm_overlap)
        + (0.15 * body_overlap)
        + (0.10 * category_overlap),
    )

    specific = specific_query_terms(q_tokens)
    if specific:
        job_tokens = title_tokens | norm_title_tokens | body_tokens | category_tokens
        if not (specific & job_tokens):
            score *= 0.35
        elif not (specific & (title_tokens | norm_title_tokens)):
            score *= 0.65

    return score


def compute_hybrid_score(*, semantic_score: float, lexical_score: float) -> float:
    ws = float(getattr(settings, "SEMANTIC_RERANK_WEIGHT_SEMANTIC", 0.55))
    wl = float(getattr(settings, "SEMANTIC_RERANK_WEIGHT_LEXICAL", 0.25))
    total = ws + wl
    if total <= 0:
        return semantic_score
    ws, wl = ws / total, wl / total
    return (ws * semantic_score) + (wl * lexical_score)


def compute_role_alignment_score(query: str, job: JobPosting) -> float:
    """
    Title/role fit beyond token overlap — rewards phrase matches and specific stack terms.
    """
    q_terms = match_terms_for_relevance(query)
    if not q_terms:
        return 0.0

    title_blob = " ".join(filter(None, [job.title, job.normalized_title])).lower()
    title_tokens = content_tokens(title_blob)
    specific = specific_query_terms(q_terms)

    if specific and is_misleading_engineer_listing(job, specific):
        return 0.0

    title_coverage = len(q_terms & title_tokens) / len(q_terms)
    specific_coverage = (
        len(specific & title_tokens) / len(specific) if specific else title_coverage
    )

    phrase_bonus = 0.0
    query_lower = (query or "").strip().lower()
    if len(q_terms) >= 2 and query_lower in title_blob:
        phrase_bonus = 0.3
    elif specific and any(term in title_blob for term in specific):
        phrase_bonus = 0.15

    return min(1.0, (0.45 * title_coverage) + (0.40 * specific_coverage) + phrase_bonus)


def compute_final_rank_score(
    *,
    semantic_score: float,
    lexical_score: float,
    role_alignment_score: float,
) -> float:
    ws = float(getattr(settings, "SEMANTIC_RERANK_WEIGHT_SEMANTIC", 0.55))
    wl = float(getattr(settings, "SEMANTIC_RERANK_WEIGHT_LEXICAL", 0.25))
    wr = float(getattr(settings, "SEMANTIC_RERANK_WEIGHT_ROLE", 0.20))
    total = ws + wl + wr
    if total <= 0:
        return semantic_score
    ws, wl, wr = ws / total, wl / total, wr / total
    return (ws * semantic_score) + (wl * lexical_score) + (wr * role_alignment_score)


def rerank_semantic_candidates(
    query: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reranked: list[dict[str, Any]] = []
    for item in candidates:
        job = item["job"]
        semantic_score = float(item["semantic_score"])
        lexical_score = compute_lexical_score(query, job)
        role_alignment_score = compute_role_alignment_score(query, job)
        hybrid_score = compute_hybrid_score(
            semantic_score=semantic_score,
            lexical_score=lexical_score,
        )
        final_rank_score = compute_final_rank_score(
            semantic_score=semantic_score,
            lexical_score=lexical_score,
            role_alignment_score=role_alignment_score,
        )
        reranked.append(
            {
                **item,
                "lexical_score": lexical_score,
                "role_alignment_score": role_alignment_score,
                "hybrid_score": hybrid_score,
                "final_rank_score": final_rank_score,
            }
        )
    reranked.sort(
        key=lambda row: (
            row["final_rank_score"],
            row["semantic_score"],
            row["role_alignment_score"],
            row["job"].posted_at or row["job"].created_at,
        ),
        reverse=True,
    )
    return reranked


def is_relevant_semantic_match(
    query: str,
    job: JobPosting,
    *,
    hybrid_score: float,
    lexical_score: float,
    semantic_score: float,
) -> bool:
    if is_domain_mismatch(query, job):
        return False

    q_terms = match_terms_for_relevance(query)
    if not q_terms:
        return semantic_score >= 0.35

    title_terms = content_tokens(" ".join(filter(None, [job.title, job.normalized_title])))
    category_terms = content_tokens(
        " ".join(filter(None, [job.category_normalized, job.category_raw]))
    )
    body_terms = content_tokens(job.description_clean or "")
    category_blob = " ".join(filter(None, [job.category_normalized, job.category_raw])).lower()

    title_hits = q_terms & title_terms
    category_hits = q_terms & category_terms
    body_hits = q_terms & body_terms
    title_prefix_hits = _prefix_overlap(q_terms, title_terms)
    category_prefix_hits = _prefix_overlap(q_terms, category_terms)
    body_prefix_hits = _prefix_overlap(q_terms, body_terms)

    specific = specific_query_terms(q_terms)
    if is_tech_query(query) and specific and is_misleading_engineer_listing(job, specific):
        return False

    if is_tech_query(query) and specific:
        if is_non_software_engineer_title(job):
            return False
        if is_software_tech_job(job) and not is_non_tech_job(job):
            title_role = title_terms & {"engineer", "developer", "programmer", "software"}
            body_blob = (job.description_clean or "").lower()
            if title_role:
                if any(_term_in_text(term, body_blob) for term in specific):
                    if semantic_score >= 0.36:
                        return True
                if semantic_score >= 0.44 and lexical_score >= 0.06:
                    return True

    if is_tech_query(query):
        if title_hits or title_prefix_hits:
            if specific and not (specific & title_terms) and len(q_terms) >= 2:
                # e.g. "backend engineer" vs "Staff Software Engineer" — engineer alone is not enough
                pass
            else:
                return True
        if (category_hits or category_prefix_hits) and any(hint in category_blob for hint in IT_CATEGORY_HINTS):
            return True
        if len(q_terms) == 1:
            term = next(iter(q_terms))
            blob = (job.description_clean or "").lower()
            if (
                body_hits
                or body_prefix_hits
                or term in blob
                or term in (job.title or "").lower()
            ) and semantic_score >= SINGLE_TERM_BODY_SEMANTIC_MIN:
                return True
        min_body_hits = 1 if len(q_terms) == 1 else 2
        if (
            len(body_hits) >= min_body_hits or body_prefix_hits
        ) and semantic_score >= 0.42 and lexical_score >= 0.08:
            return True
        return False

    if title_hits or category_hits or title_prefix_hits or category_prefix_hits:
        return True
    if (body_hits or body_prefix_hits) and semantic_score >= 0.38:
        return True
    if (body_hits or body_prefix_hits) and hybrid_score >= 0.35:
        return True
    return semantic_score >= 0.48 and lexical_score >= 0.04


def filter_relevant_semantic_results(
    query: str,
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not results:
        return []

    return [
        item
        for item in results
        if is_relevant_semantic_match(
            query,
            item["job"],
            hybrid_score=float(item.get("hybrid_score", item["semantic_score"])),
            lexical_score=float(item.get("lexical_score", 0.0)),
            semantic_score=float(item.get("semantic_score", 0.0)),
        )
    ]


def apply_relevance_with_fallback(
    query: str,
    results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Apply relevance gate; fall back when strict filtering would return zero rows."""
    filtered = filter_relevant_semantic_results(query, results)
    if filtered:
        return filtered, False

    if results and is_tech_query(query):
        specific = specific_query_terms(match_terms_for_relevance(query))
        relaxed = [
            item
            for item in results
            if not is_domain_mismatch(query, item["job"])
            and not is_misleading_engineer_listing(item["job"], specific)
            and not is_non_software_engineer_title(item["job"])
            and is_software_tech_job(item["job"])
        ]
        if relaxed:
            return relaxed, True

        if specific:
            stack_matches = [
                item
                for item in results
                if not is_domain_mismatch(query, item["job"])
                and not is_non_software_engineer_title(item["job"])
                and is_software_tech_job(item["job"])
                and has_meaningful_stack_signal(item["job"], specific)
            ]
            if stack_matches:
                return stack_matches, True

    if is_natural_language_query(query) and results:
        fallback = [item for item in results if not is_domain_mismatch(query, item["job"])]
        return (fallback or results), True
    return [], False
