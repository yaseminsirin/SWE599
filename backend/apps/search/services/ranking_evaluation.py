"""Offline evaluation helpers for hybrid ranking weight comparison."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from apps.jobs.models import JobPosting

from .retrieval_rerank import (
    _job_text_blob,
    _term_in_text,
    content_tokens,
    is_non_software_engineer_title,
    is_non_tech_job,
    is_software_tech_job,
    match_terms_for_relevance,
    specific_query_terms,
)

# Professor / report demo queries with short descriptions for the test-dataset sheet.
EVALUATION_QUERIES: tuple[tuple[str, str], ...] = (
    ("python developer", "Keyword: language + role"),
    ("data analyst", "Keyword: analytics role"),
    ("backend engineer", "Keyword: stack + role"),
    ("backend developer", "Keyword: stack + role (variant)"),
    ("software engineer", "Keyword: broad tech role"),
    ("I enjoy building backend systems and designing APIs", "Natural language intent"),
    ("dev", "Short / ambiguous query"),
)

# Five configurations compared in the Excel report (semantic, lexical, role) — sum = 1.0
WEIGHT_CONFIGS: tuple[tuple[str, str, float, float, float], ...] = (
    (
        "W1",
        "Semantic-only (100/0/0)",
        1.00,
        0.00,
        0.00,
    ),
    (
        "W2",
        "Lexical-only (0/100/0)",
        0.00,
        1.00,
        0.00,
    ),
    (
        "W3",
        "Balanced hybrid (50/50/0)",
        0.50,
        0.50,
        0.00,
    ),
    (
        "W4",
        "Neural-heavy (60/25/15)",
        0.60,
        0.25,
        0.15,
    ),
    (
        "W5",
        "JobSense default (55/25/20)",
        0.55,
        0.25,
        0.20,
    ),
)


@dataclass(frozen=True)
class RelevanceGrade:
    score: int
    reason: str


def grade_relevance(query: str, job: JobPosting) -> RelevanceGrade:
    """
    Graded relevance for evaluation (industry-style qrels: 0–3).

    0 = irrelevant, 1 = weak, 2 = relevant, 3 = highly relevant.
    Heuristic labels derived from title/category/body — suitable for report
    when human qrels are not available at scale.
    """
    title = (job.title or "").lower()
    title_tokens = content_tokens(" ".join(filter(None, [job.title, job.normalized_title])))
    body = (job.description_clean or "").lower()
    category = " ".join(
        filter(None, [job.category_normalized, job.category_raw])
    ).lower()
    blob = _job_text_blob(job)
    q_lower = query.lower()

    if is_non_tech_job(job) or is_non_software_engineer_title(job):
        return RelevanceGrade(0, "non-tech or non-software role")

    if "python developer" in q_lower or q_lower.strip() == "python developer":
        if "python" in title and "developer" in title:
            return RelevanceGrade(3, "title matches python developer")
        if "python" in title_tokens and "developer" in title_tokens:
            return RelevanceGrade(3, "title tokens python+developer")
        if "python" in title and ("developer" in body or "software" in body):
            return RelevanceGrade(2, "python title + dev context in body")
        if "python" in blob:
            return RelevanceGrade(1, "python mentioned only")
        return RelevanceGrade(0, "no python signal")

    if "data analyst" in q_lower:
        analyst_tokens = {"analyst", "analytics", "data"}
        if "data" in title_tokens and "analyst" in title_tokens:
            return RelevanceGrade(3, "data analyst title")
        if title_tokens & analyst_tokens and "data" in category:
            return RelevanceGrade(2, "analytics role")
        if title_tokens & analyst_tokens:
            return RelevanceGrade(1, "partial analyst match")
        return RelevanceGrade(0, "not analyst domain")

    if q_lower in {"backend engineer", "backend developer"} or (
        "backend" in q_lower and ("engineer" in q_lower or "developer" in q_lower)
    ):
        if "backend" in title_tokens:
            return RelevanceGrade(3, "backend in title")
        if is_software_tech_job(job) and _term_in_text("backend", body):
            return RelevanceGrade(2, "software role + backend in body")
        if title_tokens & {"software", "computer", "developer", "engineer"}:
            if "software" in title_tokens or "engineering" in title:
                return RelevanceGrade(2, "software engineering leadership/role")
            if title_tokens & {"developer", "engineer"}:
                return RelevanceGrade(1, "generic software engineer/developer")
        return RelevanceGrade(0, "not backend/software fit")

    if "software engineer" in q_lower:
        if "software" in title_tokens and "engineer" in title_tokens:
            return RelevanceGrade(3, "software engineer title")
        if title_tokens & {"software", "engineer", "developer", "computer"}:
            return RelevanceGrade(2, "close software role")
        return RelevanceGrade(0, "not software engineering")

    if any(
        phrase in q_lower
        for phrase in ("i enjoy", "building backend", "designing api", "apis")
    ):
        if _term_in_text("backend", body) and title_tokens & {"engineer", "developer", "software"}:
            return RelevanceGrade(3, "NL backend builder match")
        if title_tokens & {"software", "engineer", "developer"} and (
            _term_in_text("api", body) or _term_in_text("backend", body)
        ):
            return RelevanceGrade(2, "software + API/backend body")
        if is_software_tech_job(job):
            return RelevanceGrade(1, "generic software")
        return RelevanceGrade(0, "off-topic")

    if q_lower.strip() == "dev":
        if title_tokens & {"developer", "devops", "engineer"}:
            return RelevanceGrade(2, "developer/devops title")
        if "dev" in title_tokens or any(t.startswith("dev") for t in title_tokens):
            return RelevanceGrade(1, "dev prefix in title")
        return RelevanceGrade(0, "no dev signal")

    # Fallback: token overlap
    q_terms = match_terms_for_relevance(query)
    if not q_terms:
        return RelevanceGrade(0, "no query terms")
    overlap = len(q_terms & content_tokens(blob))
    if overlap >= 2:
        return RelevanceGrade(2, f"token overlap={overlap}")
    if overlap == 1:
        return RelevanceGrade(1, "single token overlap")
    return RelevanceGrade(0, "no overlap")


def final_score_with_weights(
    *,
    semantic_score: float,
    lexical_score: float,
    role_alignment_score: float,
    ws: float,
    wl: float,
    wr: float,
) -> float:
    total = ws + wl + wr
    if total <= 0:
        return semantic_score
    ws, wl, wr = ws / total, wl / total, wr / total
    return (ws * semantic_score) + (wl * lexical_score) + (wr * role_alignment_score)


def rank_with_weights(
    pool: list[dict[str, Any]],
    *,
    ws: float,
    wl: float,
    wr: float,
) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for item in pool:
        score = final_score_with_weights(
            semantic_score=float(item["semantic_score"]),
            lexical_score=float(item.get("lexical_score", 0.0)),
            role_alignment_score=float(item.get("role_alignment_score", 0.0)),
            ws=ws,
            wl=wl,
            wr=wr,
        )
        scored.append({**item, "eval_score": score})
    scored.sort(
        key=lambda row: (
            row["eval_score"],
            row["semantic_score"],
            row.get("role_alignment_score", 0.0),
            row["job"].posted_at or row["job"].created_at,
        ),
        reverse=True,
    )
    return scored


def dcg_at_k(grades: list[int], k: int) -> float:
    total = 0.0
    for index, grade in enumerate(grades[:k], start=1):
        if grade <= 0:
            continue
        total += (2**grade - 1) / math.log2(index + 1)
    return total


def ndcg_at_k(grades: list[int], k: int) -> float:
    if not grades:
        return 0.0
    ideal = sorted(grades, reverse=True)
    denom = dcg_at_k(ideal, k)
    if denom <= 0:
        return 0.0
    return dcg_at_k(grades, k) / denom


def mrr_at_k(grades: list[int], k: int, *, min_relevant: int = 2) -> float:
    for index, grade in enumerate(grades[:k], start=1):
        if grade >= min_relevant:
            return 1.0 / index
    return 0.0


def precision_at_k(grades: list[int], k: int, *, min_relevant: int = 2) -> float:
    if k <= 0:
        return 0.0
    hits = sum(1 for grade in grades[:k] if grade >= min_relevant)
    return hits / k
