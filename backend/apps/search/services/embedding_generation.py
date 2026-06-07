import logging
import time
from typing import Any

from django.conf import settings
from django.db.models import Case, IntegerField, QuerySet, When

from apps.jobs.models import JobPosting
from apps.search.models import JobEmbedding
from apps.search.services.embeddings.factory import (
    get_embedding_provider,
)
from apps.search.services.job_quality import get_searchable_job_queryset

from .embeddings.factory import (
    EmbeddingProviderError,
    embed_text_with_metadata,
    is_embedding_strict_mode,
    log_embedding_usage,
)
from .embeddings.types import EmbeddingResult

logger = logging.getLogger(__name__)

# Final-demo priority: high-signal sources first, USAJOBS last.
SOURCE_EMBED_PRIORITY = ("remotive", "adzuna", "usajobs")


def build_job_embedding_text(job: JobPosting) -> str:
    """
    Title-first text for MiniLM — job titles carry most retrieval signal; full
    descriptions dilute vectors. Re-run regenerate_embeddings after changing this.
    """
    title_line = " ".join(
        filter(
            None,
            [
                job.title,
                job.normalized_title,
                job.category_normalized,
                job.category_raw,
            ],
        )
    )
    description = (job.description_clean or "")[:700]
    return "\n".join(
        [
            f"role: {title_line}",
            f"company: {job.company_name or ''}",
            f"location: {job.location_text or ''}",
            f"summary: {description}",
        ]
    ).strip()


def _is_quota_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        token in message
        for token in ("429", "quota", "resource exhausted", "rate limit", "too many requests")
    )


def _assert_strict_embedding_allowed(result: EmbeddingResult) -> None:
    if not is_embedding_strict_mode():
        return
    if result.fallback_triggered or result.provider_substituted:
        detail = result.error_message or "provider unavailable"
        raise EmbeddingProviderError(
            f"EMBEDDING_STRICT_PROVIDER blocked embedding generation: {detail}"
        )


def _resolve_regeneration_defaults(
    *,
    source: str | None,
    tech_only: bool | None,
    limit: int | None,
    batch_size: int | None,
    sleep_seconds: float | None,
) -> dict[str, Any]:
    env_source = (getattr(settings, "EMBEDDING_SOURCE_FILTER", "") or "").strip() or None
    env_tech = getattr(settings, "EMBEDDING_TECH_ONLY", None)
    return {
        "source": source if source is not None else env_source,
        "tech_only": tech_only if tech_only is not None else env_tech,
        "limit": limit if limit is not None else getattr(settings, "EMBEDDING_MAX_JOBS_PER_RUN", 0) or None,
        "batch_size": batch_size or getattr(settings, "EMBEDDING_BATCH_SIZE", 50),
        "sleep_seconds": sleep_seconds if sleep_seconds is not None else getattr(settings, "EMBEDDING_SLEEP_SECONDS", 0.0),
    }


def get_embedding_candidate_queryset(
    *,
    source: str | None = None,
    tech_only: bool | None = None,
    missing_only: bool = True,
) -> QuerySet[JobPosting]:
    """Jobs eligible for embedding, ordered for demo priority when source is not fixed."""
    if tech_only is None:
        tech_only = getattr(settings, "SEMANTIC_TECH_ONLY", True)

    queryset = get_searchable_job_queryset(
        real_sources_only=True,
        exclude_demo=True,
        tech_only=tech_only,
    )
    if source:
        queryset = queryset.filter(source=source).order_by("-posted_at", "-created_at")
    else:
        queryset = queryset.annotate(
            source_priority=Case(
                When(source="remotive", then=0),
                When(source="adzuna", then=1),
                When(source="usajobs", then=2),
                default=9,
                output_field=IntegerField(),
            )
        ).order_by("source_priority", "-posted_at", "-created_at")

    if missing_only:
        provider = get_embedding_provider()
        queryset = queryset.exclude(
            embeddings__provider=provider.provider_name,
            embeddings__model_name=provider.model_name,
        )
    return queryset


def generate_job_embedding(job: JobPosting, *, force: bool = False) -> JobEmbedding:
    text = build_job_embedding_text(job)
    result = embed_text_with_metadata(text, task_type="RETRIEVAL_DOCUMENT")
    _assert_strict_embedding_allowed(result)
    log_embedding_usage(result, context="job_embedding", text_preview=job.title or "")

    if len(result.vector) != result.dimension:
        raise ValueError(
            f"Embedding dimension mismatch: got {len(result.vector)}, expected {result.dimension}"
        )

    lookup = {
        "job": job,
        "provider": result.provider_name,
        "model_name": result.model_name,
    }
    if force:
        JobEmbedding.objects.filter(**lookup).delete()

    embedding, _ = JobEmbedding.objects.update_or_create(
        **lookup,
        defaults={
            "vector_dimension": result.dimension,
            "embedding": result.vector,
        },
    )
    return embedding


def _persist_job_embedding(job: JobPosting, vector: list[float], provider) -> None:
    JobEmbedding.objects.update_or_create(
        job=job,
        provider=provider.provider_name,
        model_name=provider.model_name,
        defaults={
            "vector_dimension": len(vector),
            "embedding": vector,
        },
    )


def _embed_jobs_with_provider(jobs: list[JobPosting], provider) -> None:
    if hasattr(provider, "embed_texts"):
        texts = [build_job_embedding_text(job) for job in jobs]
        vectors = provider.embed_texts(texts)
        if len(vectors) != len(jobs):
            raise ValueError("Batch embedding returned unexpected row count")
        for job, vector in zip(jobs, vectors, strict=True):
            _persist_job_embedding(job, vector, provider)
        return

    for job in jobs:
        result = embed_text_with_metadata(
            build_job_embedding_text(job),
            task_type="RETRIEVAL_DOCUMENT",
        )
        _assert_strict_embedding_allowed(result)
        _persist_job_embedding(job, result.vector, provider)


def regenerate_job_embeddings(
    *,
    source: str | None = None,
    tech_only: bool | None = None,
    limit: int | None = None,
    batch_size: int | None = None,
    sleep_seconds: float | None = None,
    missing_only: bool = True,
    force: bool = False,
) -> dict[str, int | bool | str | None]:
    """
    Embed jobs incrementally (missing-only by default) with quota-safe pacing.
    Does not delete real JobPosting rows. Use force=True to replace existing vectors.
    """
    resolved = _resolve_regeneration_defaults(
        source=source,
        tech_only=tech_only,
        limit=limit,
        batch_size=batch_size,
        sleep_seconds=sleep_seconds,
    )
    source = resolved["source"]
    tech_only = resolved["tech_only"]
    limit = resolved["limit"]
    batch_size = resolved["batch_size"]
    sleep_seconds = resolved["sleep_seconds"]
    configured = settings.EMBEDDING_PROVIDER.lower().strip()
    stop_on_quota = (
        getattr(settings, "EMBEDDING_STOP_ON_QUOTA", True)
        and configured == "gemini"
    )

    if missing_only and force:
        missing_only = False

    jobs_qs = get_embedding_candidate_queryset(
        source=source,
        tech_only=tech_only,
        missing_only=missing_only,
    )
    if limit and limit > 0:
        job_ids = list(jobs_qs.values_list("id", flat=True)[:limit])
        jobs_qs = JobPosting.objects.filter(id__in=job_ids).order_by("id")
        if not source:
            jobs_qs = jobs_qs.annotate(
                source_priority=Case(
                    When(source="remotive", then=0),
                    When(source="adzuna", then=1),
                    When(source="usajobs", then=2),
                    default=9,
                    output_field=IntegerField(),
                )
            ).order_by("source_priority", "-posted_at", "-created_at")

    provider = get_embedding_provider()
    job_ids = list(jobs_qs.values_list("id", flat=True))
    candidates = len(job_ids)

    deleted = 0
    if force and job_ids:
        deleted, _ = JobEmbedding.objects.filter(
            job_id__in=job_ids,
            provider=provider.provider_name,
            model_name=provider.model_name,
        ).delete()

    regenerated = 0
    errors = 0
    primary_count = 0
    fallback_count = 0
    substituted_count = 0
    stopped_on_quota = False
    last_error: str | None = None

    use_batch_encode = hasattr(provider, "embed_texts")
    pending: list[JobPosting] = []

    def flush_batch(batch: list[JobPosting]) -> None:
        nonlocal regenerated, errors, primary_count, last_error, stopped_on_quota
        if not batch:
            return
        try:
            _embed_jobs_with_provider(batch, provider)
            regenerated += len(batch)
            primary_count += len(batch)
            logger.info(
                "embedding_batch_complete size=%d provider=%s/%s",
                len(batch),
                provider.provider_name,
                provider.model_name,
            )
        except EmbeddingProviderError as exc:
            errors += len(batch)
            last_error = str(exc)
            logger.error("embedding_batch_failed size=%d error=%s", len(batch), exc)
            if stop_on_quota and _is_quota_error(exc):
                stopped_on_quota = True
        except Exception as exc:
            errors += len(batch)
            last_error = str(exc)
            logger.warning("embedding_batch_failed size=%d error=%s", len(batch), exc)
            if stop_on_quota and is_embedding_strict_mode() and _is_quota_error(exc):
                stopped_on_quota = True

    for index, job in enumerate(jobs_qs.iterator(chunk_size=batch_size), start=1):
        if stopped_on_quota:
            break

        if use_batch_encode:
            pending.append(job)
            if len(pending) >= batch_size:
                flush_batch(pending)
                pending = []
                if sleep_seconds > 0 and index < candidates:
                    time.sleep(sleep_seconds)
            continue

        try:
            result = embed_text_with_metadata(
                build_job_embedding_text(job),
                task_type="RETRIEVAL_DOCUMENT",
            )
            _assert_strict_embedding_allowed(result)
            _persist_job_embedding(job, result.vector, provider)
            regenerated += 1
            if result.fallback_triggered:
                fallback_count += 1
            elif result.provider_substituted:
                substituted_count += 1
            else:
                primary_count += 1
        except EmbeddingProviderError as exc:
            errors += 1
            last_error = str(exc)
            logger.error(
                "job_embedding_failed job_id=%s source=%s title=%r strict_error=%s",
                job.id,
                job.source,
                (job.title or "")[:80],
                exc,
            )
            if stop_on_quota and _is_quota_error(exc):
                stopped_on_quota = True
                logger.error("embedding_run_stopped_on_quota after %d successes", regenerated)
                break
        except Exception as exc:
            errors += 1
            last_error = str(exc)
            logger.warning(
                "job_embedding_failed job_id=%s source=%s title=%r error=%s",
                job.id,
                job.source,
                (job.title or "")[:80],
                exc,
            )
            if stop_on_quota and is_embedding_strict_mode() and _is_quota_error(exc):
                stopped_on_quota = True
                logger.error("embedding_run_stopped_on_quota after %d successes", regenerated)
                break

        if sleep_seconds > 0 and index < candidates:
            time.sleep(sleep_seconds)

    if use_batch_encode and pending and not stopped_on_quota:
        flush_batch(pending)

    logger.info(
        "embedding_regeneration_complete configured=%s provider=%s/%s source=%s tech_only=%s "
        "candidates=%d deleted=%d regenerated=%d primary=%d fallback=%d substituted=%d "
        "failed=%d stopped_on_quota=%s",
        configured,
        provider.provider_name,
        provider.model_name,
        source or "all(priority)",
        tech_only,
        candidates,
        deleted,
        regenerated,
        primary_count,
        fallback_count,
        substituted_count,
        errors,
        stopped_on_quota,
    )

    return {
        "candidates": candidates,
        "deleted": deleted,
        "regenerated": regenerated,
        "primary": primary_count,
        "fallback": fallback_count,
        "substituted": substituted_count,
        "errors": errors,
        "stopped_on_quota": stopped_on_quota,
        "last_error": last_error,
        "source": source,
        "tech_only": tech_only,
        "limit": limit,
    }


def regenerate_all_job_embeddings(
    *,
    batch_size: int = 200,
    source: str | None = None,
) -> dict[str, int | bool | str | None]:
    """Backward-compatible wrapper: rebuild missing jobs (or one source) without mass delete."""
    return regenerate_job_embeddings(
        source=source,
        tech_only=False,
        missing_only=not bool(source),
        force=bool(source),
        batch_size=batch_size,
        limit=None,
    )
