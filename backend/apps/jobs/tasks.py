from celery import shared_task

from apps.search.tasks import generate_missing_job_embeddings_task

from .services.ingestion_pipeline import (
    ingest_all_sources,
    ingest_source,
    normalize_all_pending,
)
from .services.normalization_pipeline import normalize_raw_records_batch


@shared_task
def ingest_all_sources_task(*, sync: bool = True) -> dict:
    """Run ingestion for all sources; isolate per-source failures."""
    return ingest_all_sources(sync=sync)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def ingest_source_task(self, source: str, *, sync: bool = True) -> dict:
    """Run ingestion for one source with task-level retry support."""
    return ingest_source(source, sync=sync)


@shared_task
def normalize_raw_records_task(batch_size: int = 100) -> dict:
    """Normalize unprocessed RawJobRecord rows into JobPosting."""
    return normalize_raw_records_batch(batch_size=batch_size)


@shared_task
def nightly_job_refresh_task() -> dict:
    """
    Full nightly sync: fetch max jobs per source, prune stale rows,
    normalize pending records, generate missing embeddings.
    """
    ingest_summary = ingest_all_sources(sync=True)
    normalize_summary = normalize_all_pending()
    embedding_summary = generate_missing_job_embeddings_task()

    return {
        "ingest": ingest_summary,
        "normalize": normalize_summary,
        "embeddings": embedding_summary,
    }
