from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.jobs.models import JobPosting, RawJobRecord

from .normalizers import NORMALIZERS


def _apply_normalized_fields(job: JobPosting, normalized: dict[str, Any], *, include_source_fields: bool) -> None:
    common_fields = [
        "title",
        "normalized_title",
        "company_name",
        "description_raw",
        "description_clean",
        "job_url",
        "location_text",
        "city",
        "country",
        "is_remote",
        "employment_type",
        "posted_at",
        "expires_at",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_period",
        "category_raw",
        "category_normalized",
        "content_hash",
        "fetched_at",
        "normalized_at",
    ]
    if include_source_fields:
        common_fields.extend(["source", "source_job_id", "raw_record"])

    for field in common_fields:
        if field in normalized:
            setattr(job, field, normalized[field])


def _normalize_single_record(raw_record: RawJobRecord) -> str:
    normalizer_cls = NORMALIZERS.get(raw_record.source)
    if normalizer_cls is None:
        raise ValueError(f"No normalizer for source={raw_record.source}")
    normalizer = normalizer_cls()
    normalized = normalizer.normalize(raw_record.payload, source_job_id=raw_record.source_job_id)

    # MVP fallbacks: always keep minimal searchable/displayable fields.
    normalized["title"] = (normalized.get("title") or "").strip() or f"Job {raw_record.source_job_id}"
    normalized["job_url"] = (normalized.get("job_url") or "").strip() or (
        f"https://example.invalid/jobs/{raw_record.source}/{raw_record.source_job_id}"
    )
    normalized["description_clean"] = (
        (normalized.get("description_clean") or "").strip()
        or (normalized.get("description_raw") or "").strip()
        or normalized["title"]
    )

    normalized["source"] = raw_record.source
    normalized["source_job_id"] = raw_record.source_job_id
    normalized["raw_record"] = raw_record
    normalized["fetched_at"] = raw_record.fetched_at
    normalized["normalized_at"] = timezone.now()

    with transaction.atomic():
        # 1) Primary traceability: same source + source_job_id -> update existing posting.
        existing_same_source = JobPosting.objects.filter(
            source=raw_record.source,
            source_job_id=raw_record.source_job_id,
        ).first()
        if existing_same_source:
            _apply_normalized_fields(existing_same_source, normalized, include_source_fields=False)
            existing_same_source.raw_record = raw_record
            existing_same_source.save()
            raw_record.normalized_job = existing_same_source
            raw_record.processed_at = timezone.now()
            raw_record.save(update_fields=["normalized_job", "processed_at", "updated_at"])
            return "updated"

        # 2) Conservative cross-source dedupe: if content hash exists, skip new posting.
        duplicate_by_hash = JobPosting.objects.filter(content_hash=normalized["content_hash"]).first()
        if duplicate_by_hash:
            raw_record.normalized_job = duplicate_by_hash
            raw_record.processed_at = timezone.now()
            raw_record.save(update_fields=["normalized_job", "processed_at", "updated_at"])
            return "duplicate"

        # 3) No match -> create new posting.
        posting = JobPosting()
        _apply_normalized_fields(posting, normalized, include_source_fields=True)
        posting.save()
        raw_record.normalized_job = posting
        raw_record.processed_at = timezone.now()
        raw_record.save(update_fields=["normalized_job", "processed_at", "updated_at"])
        return "created"


def normalize_raw_records_batch(*, batch_size: int = 100) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "raw_records_seen": 0,
        "normalized_created": 0,
        "normalized_updated": 0,
        "duplicates_merged_skipped": 0,
        "normalization_errors": [],
    }

    raw_records = (
        RawJobRecord.objects.filter(processed_at__isnull=True)
        .order_by("fetched_at", "id")[:batch_size]
    )

    for raw_record in raw_records:
        summary["raw_records_seen"] += 1
        try:
            action = _normalize_single_record(raw_record)
            if action == "created":
                summary["normalized_created"] += 1
            elif action == "updated":
                summary["normalized_updated"] += 1
            elif action == "duplicate":
                summary["duplicates_merged_skipped"] += 1
        except Exception as exc:
            summary["normalization_errors"].append(
                {
                    "raw_record_id": raw_record.id,
                    "source": raw_record.source,
                    "source_job_id": raw_record.source_job_id,
                    "error": str(exc),
                }
            )

    return summary
