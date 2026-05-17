import os
from typing import Any

from django.db import transaction

from apps.jobs.models import JobPosting, RawJobRecord

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


def get_page_size_for_source(source: str) -> int:
    source_key = source.upper()
    return _env_int(f"INGEST_PAGE_SIZE_{source_key}", get_page_size())


def get_max_pages_for_source(source: str) -> int:
    source_key = source.upper()
    return _env_int(f"INGEST_MAX_PAGES_{source_key}", _env_int("INGEST_MAX_PAGES", 50))


def save_raw_record(raw_record: dict[str, Any]) -> bool:
    """Return True when created, False when duplicate skipped (legacy exact-payload match)."""
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


def upsert_raw_record(raw_record: dict[str, Any]) -> tuple[bool, bool]:
    """Upsert by source + source_job_id. Returns (created, updated)."""
    payload = raw_record["payload"]
    source = raw_record["source"]
    source_job_id = raw_record["source_job_id"]
    fetched_at = raw_record["fetched_at"]

    with transaction.atomic():
        existing = (
            RawJobRecord.objects.filter(source=source, source_job_id=source_job_id)
            .order_by("-id")
            .first()
        )
        if existing is None:
            RawJobRecord.objects.create(
                source=source,
                source_job_id=source_job_id,
                payload=payload,
                fetched_at=fetched_at,
                processed_at=None,
            )
            return True, False

        changed = existing.payload != payload
        existing.payload = payload
        existing.fetched_at = fetched_at
        existing.processed_at = None
        existing.save(update_fields=["payload", "fetched_at", "processed_at", "updated_at"])
        return False, changed


def prune_stale_jobs(source: str, active_source_job_ids: set[str]) -> dict[str, int]:
    """Remove postings and raw rows for this source that were not in the latest fetch."""
    stale_postings = JobPosting.objects.filter(source=source).exclude(
        source_job_id__in=active_source_job_ids
    )
    deleted_postings, _ = stale_postings.delete()

    stale_raw = RawJobRecord.objects.filter(source=source).exclude(
        source_job_id__in=active_source_job_ids
    )
    deleted_raw, _ = stale_raw.delete()

    return {
        "deleted_postings": deleted_postings,
        "deleted_raw_records": deleted_raw,
    }


def ingest_source(source: str, *, sync: bool = True) -> dict[str, Any]:
    adapter_cls = ADAPTERS.get(source)
    if adapter_cls is None:
        raise ValueError(f"Unsupported source: {source}")

    adapter = adapter_cls()
    page_size = get_page_size_for_source(source)
    max_pages = get_max_pages_for_source(source)

    result: dict[str, Any] = {
        "source": source,
        "sync": sync,
        "max_pages": max_pages,
        "page_size": page_size,
        "pages_attempted": 0,
        "fetched_records": 0,
        "created_records": 0,
        "updated_records": 0,
        "duplicate_records": 0,
        "active_source_job_ids": [],
        "pruned": {},
        "errors": [],
    }

    active_ids: set[str] = set()
    seen_page_ids: set[str] = set()

    for page in range(1, max_pages + 1):
        result["pages_attempted"] += 1
        records = adapter.fetch_jobs(page=page, per_page=page_size)
        if not records:
            break

        page_ids = {str(record["source_job_id"]) for record in records}
        if page > 1 and page_ids and page_ids <= seen_page_ids:
            break
        seen_page_ids |= page_ids

        result["fetched_records"] += len(records)
        for record in records:
            job_id = str(record["source_job_id"])
            active_ids.add(job_id)
            if sync:
                created, updated = upsert_raw_record(record)
                if created:
                    result["created_records"] += 1
                elif updated:
                    result["updated_records"] += 1
                else:
                    result["duplicate_records"] += 1
            else:
                created = save_raw_record(record)
                if created:
                    result["created_records"] += 1
                else:
                    result["duplicate_records"] += 1

    result["active_source_job_ids"] = sorted(active_ids)

    if sync and active_ids:
        result["pruned"] = prune_stale_jobs(source, active_ids)

    return result


def ingest_all_sources(*, sync: bool = True) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "sync": sync,
        "sources": {},
        "total_fetched": 0,
        "total_created": 0,
        "total_updated": 0,
        "total_duplicates": 0,
        "total_pruned_postings": 0,
        "total_pruned_raw_records": 0,
        "failed_sources": [],
    }

    for source in ADAPTERS.keys():
        try:
            source_result = ingest_source(source, sync=sync)
            summary["sources"][source] = source_result
            summary["total_fetched"] += source_result["fetched_records"]
            summary["total_created"] += source_result["created_records"]
            summary["total_updated"] += source_result.get("updated_records", 0)
            summary["total_duplicates"] += source_result["duplicate_records"]
            pruned = source_result.get("pruned") or {}
            summary["total_pruned_postings"] += pruned.get("deleted_postings", 0)
            summary["total_pruned_raw_records"] += pruned.get("deleted_raw_records", 0)
        except Exception as exc:
            summary["failed_sources"].append(source)
            summary["sources"][source] = {
                "source": source,
                "error": str(exc),
            }

    return summary


def normalize_all_pending(*, batch_size: int = 500, max_rounds: int = 200) -> dict[str, Any]:
    from .normalization_pipeline import normalize_raw_records_batch

    totals: dict[str, Any] = {
        "rounds": 0,
        "raw_records_seen": 0,
        "normalized_created": 0,
        "normalized_updated": 0,
        "duplicates_merged_skipped": 0,
        "normalization_errors": [],
    }

    for _ in range(max_rounds):
        batch = normalize_raw_records_batch(batch_size=batch_size)
        totals["rounds"] += 1
        totals["raw_records_seen"] += batch["raw_records_seen"]
        totals["normalized_created"] += batch["normalized_created"]
        totals["normalized_updated"] += batch["normalized_updated"]
        totals["duplicates_merged_skipped"] += batch["duplicates_merged_skipped"]
        totals["normalization_errors"].extend(batch["normalization_errors"])
        if batch["raw_records_seen"] == 0:
            break

    return totals
