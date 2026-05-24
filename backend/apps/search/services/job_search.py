from django.db.models import F, Q, QuerySet

from apps.jobs.models import JobPosting

from .job_quality import apply_keyword_token_filter, get_searchable_job_queryset


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def get_base_job_queryset(*, include_demo: bool = False) -> QuerySet[JobPosting]:
    if include_demo:
        return JobPosting.objects.all().order_by(
            F("posted_at").desc(nulls_last=True),
            "-created_at",
        )
    return get_searchable_job_queryset(
        real_sources_only=True,
        exclude_demo=True,
        tech_only=False,
    ).order_by(F("posted_at").desc(nulls_last=True), "-created_at")


def apply_job_filters(queryset: QuerySet[JobPosting], params: dict[str, str]) -> QuerySet[JobPosting]:
    keyword = (params.get("keyword") or "").strip()
    location = (params.get("location") or "").strip()
    employment_type = (params.get("employment_type") or "").strip()
    is_remote = _parse_bool(params.get("is_remote"))

    if keyword:
        queryset = apply_keyword_token_filter(queryset, keyword)

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
