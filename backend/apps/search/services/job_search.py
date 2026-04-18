from django.db.models import F, Q, QuerySet

from apps.jobs.models import JobPosting


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def get_base_job_queryset() -> QuerySet[JobPosting]:
    return JobPosting.objects.all().order_by(F("posted_at").desc(nulls_last=True), "-created_at")


def apply_job_filters(queryset: QuerySet[JobPosting], params: dict[str, str]) -> QuerySet[JobPosting]:
    keyword = (params.get("keyword") or "").strip()
    location = (params.get("location") or "").strip()
    employment_type = (params.get("employment_type") or "").strip()
    is_remote = _parse_bool(params.get("is_remote"))

    if keyword:
        queryset = queryset.filter(
            Q(title__icontains=keyword)
            | Q(description_clean__icontains=keyword)
        )

    if location:
        queryset = queryset.filter(
            Q(city__icontains=location)
            | Q(country__icontains=location)
            | Q(location_text__icontains=location)
        )

    if is_remote is not None:
        queryset = queryset.filter(is_remote=is_remote)

    if employment_type:
        queryset = queryset.filter(employment_type__iexact=employment_type)

    return queryset
