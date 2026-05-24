from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.jobs.models import JobPosting, RawJobRecord
from apps.jobs.services.normalizers.base import build_content_hash, clean_text
from apps.search.models import JobEmbedding

from .demo_dataset import DEMO_SOURCE, iter_demo_job_dicts


def clear_demo_jobs() -> dict[str, int]:
    """Remove all demo-source jobs and related rows."""
    demo_job_ids = list(
        JobPosting.objects.filter(source=DEMO_SOURCE).values_list("id", flat=True)
    )
    embeddings_deleted, _ = JobEmbedding.objects.filter(job_id__in=demo_job_ids).delete()
    postings_deleted, _ = JobPosting.objects.filter(source=DEMO_SOURCE).delete()
    raw_deleted, _ = RawJobRecord.objects.filter(source=DEMO_SOURCE).delete()
    return {
        "job_postings_deleted": postings_deleted,
        "raw_records_deleted": raw_deleted,
        "embeddings_deleted": embeddings_deleted,
    }


def isolate_demo_embeddings(*, provider_name: str, model_name: str) -> int:
    """Drop embeddings for non-demo jobs so semantic search is demo-focused."""
    deleted, _ = (
        JobEmbedding.objects.filter(provider=provider_name, model_name=model_name)
        .exclude(job__source=DEMO_SOURCE)
        .delete()
    )
    return deleted


@transaction.atomic
def seed_demo_jobs(*, reset: bool = False) -> dict[str, Any]:
    if reset:
        clear_demo_jobs()

    created = 0
    now = timezone.now()
    for job_data in iter_demo_job_dicts():
        slug = job_data["slug"]
        normalized_title = clean_text(job_data["title"]).lower()
        content_hash = build_content_hash(
            normalized_title=normalized_title,
            company_name=job_data["company_name"],
            location_text=job_data["location_text"],
            description_clean=job_data["description_clean"],
        )

        payload = {
            "demo": True,
            "slug": slug,
            "title": job_data["title"],
            "company": job_data["company_name"],
            "category": job_data["category_normalized"],
        }
        raw, _ = RawJobRecord.objects.update_or_create(
            source=DEMO_SOURCE,
            source_job_id=slug,
            defaults={
                "payload": payload,
                "fetched_at": now,
                "processed_at": now,
            },
        )

        posting, was_created = JobPosting.objects.update_or_create(
            source=DEMO_SOURCE,
            source_job_id=slug,
            defaults={
                "raw_record": raw,
                "title": job_data["title"],
                "normalized_title": normalized_title,
                "company_name": job_data["company_name"],
                "description_raw": job_data["description_raw"],
                "description_clean": job_data["description_clean"],
                "job_url": job_data["job_url"],
                "location_text": job_data["location_text"],
                "city": job_data["city"],
                "country": job_data["country"],
                "is_remote": job_data["is_remote"],
                "employment_type": job_data["employment_type"],
                "posted_at": job_data["posted_at"],
                "category_raw": job_data["category_normalized"],
                "category_normalized": job_data["category_normalized"],
                "content_hash": content_hash,
                "fetched_at": now,
                "normalized_at": now,
            },
        )
        raw.normalized_job = posting
        raw.save(update_fields=["normalized_job", "updated_at"])
        if was_created:
            created += 1

    return {
        "demo_jobs_total": JobPosting.objects.filter(source=DEMO_SOURCE).count(),
        "demo_jobs_created": created,
        "reset_applied": reset,
    }
