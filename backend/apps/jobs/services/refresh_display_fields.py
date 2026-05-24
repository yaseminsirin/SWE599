from apps.jobs.models import JobPosting, RawJobRecord
from apps.jobs.services.normalizers import NORMALIZERS


def refresh_job_display_fields_from_raw() -> dict:
    """Re-apply normalizers to fix employment_type / is_remote on existing postings."""
    updated = 0
    skipped = 0
    for job in JobPosting.objects.iterator():
        raw = job.raw_record
        if raw is None:
            raw = (
                RawJobRecord.objects.filter(source=job.source, source_job_id=job.source_job_id)
                .order_by("-fetched_at")
                .first()
            )
        if raw is None:
            skipped += 1
            continue
        normalizer_cls = NORMALIZERS.get(job.source)
        if normalizer_cls is None:
            skipped += 1
            continue
        data = normalizer_cls().normalize(raw.payload, source_job_id=job.source_job_id)
        fields: list[str] = []
        if job.employment_type != data.get("employment_type", ""):
            job.employment_type = data.get("employment_type", "")
            fields.append("employment_type")
        if job.is_remote != data.get("is_remote", False):
            job.is_remote = bool(data.get("is_remote", False))
            fields.append("is_remote")
        if fields:
            job.save(update_fields=fields + ["updated_at"])
            updated += 1
    return {"updated": updated, "skipped": skipped}
