import os
from typing import Any

from django.db import transaction

from apps.jobs.models import RawJobRecord

from .source_ingestion import ADAPTERS


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, str(default)).strip()
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except ValueError:
        return default


def get_page_size() -> int:
    return _env_int("INGEST_PAGE_SIZE", 50)


def get_max_pages_for_source(source: str) -> int:
    source_key = source.upper()
    return _env_int(f"INGEST_MAX_PAGES_{source_key}", _env_int("INGEST_MAX_PAGES", 3))


def save_raw_record(raw_record: dict[str, Any]) -> bool:
    """Return True when created, False when duplicate skipped."""
    payload = raw_record["payload"]
    source = raw_record["source"]
    source_job_id = raw_record["source_job_id"]
    fetched_at = raw_record["fetched_at"]

    with transaction.atomic():
        _, created = RawJobRecord.objects.get_or_create(
            source=source,
            source_job_id=source_job_id,
            payload=payload,
            defaults={
                "fetched_at": fetched_at,
                "processed_at": None,
            },
        )
    return created


def ingest_source(source: str) -> dict[str, Any]:
    adapter_cls = ADAPTERS.get(source)
    if adapter_cls is None:
        raise ValueError(f"Unsupported source: {source}")

    adapter = adapter_cls()
    page_size = get_page_size()
    max_pages = get_max_pages_for_source(source)

    result: dict[str, Any] = {
        "source": source,
        "max_pages": max_pages,
        "page_size": page_size,
        "pages_attempted": 0,
        "fetched_records": 0,
        "created_records": 0,
        "duplicate_records": 0,
        "errors": [],
    }

    for page in range(1, max_pages + 1):
        result["pages_attempted"] += 1
        records = adapter.fetch_jobs(page=page, per_page=page_size)
        if not records:
            break

        result["fetched_records"] += len(records)
        for record in records:
            created = save_raw_record(record)
            if created:
                result["created_records"] += 1
            else:
                result["duplicate_records"] += 1

    return result


def ingest_all_sources() -> dict[str, Any]:
    summary: dict[str, Any] = {
        "sources": {},
        "total_fetched": 0,
        "total_created": 0,
        "total_duplicates": 0,
        "failed_sources": [],
    }

    for source in ADAPTERS.keys():
        try:
            source_result = ingest_source(source)
            summary["sources"][source] = source_result
            summary["total_fetched"] += source_result["fetched_records"]
            summary["total_created"] += source_result["created_records"]
            summary["total_duplicates"] += source_result["duplicate_records"]
        except Exception as exc:
            summary["failed_sources"].append(source)
            summary["sources"][source] = {
                "source": source,
                "error": str(exc),
            }

    return summary
