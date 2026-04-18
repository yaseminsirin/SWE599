from celery import shared_task

from .services.ingestion_pipeline import ingest_all_sources, ingest_source
from .services.normalization_pipeline import normalize_raw_records_batch


@shared_task
def ingest_all_sources_task() -> dict:
    """Run ingestion for all sources; isolate per-source failures."""
    return ingest_all_sources()


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def ingest_source_task(self, source: str) -> dict:
    """Run ingestion for one source with task-level retry support."""
    return ingest_source(source)


@shared_task
def normalize_raw_records_task(batch_size: int = 100) -> dict:
    """Normalize unprocessed RawJobRecord rows into JobPosting."""
    return normalize_raw_records_batch(batch_size=batch_size)
