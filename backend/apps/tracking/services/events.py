from typing import Any

from apps.jobs.models import JobPosting

from ..models import JobClickEvent, UserSearchEvent


def record_search_event(
    *,
    user,
    query: str,
    filters: dict[str, Any] | None = None,
    result_count: int = 0,
    response_ms: int | None = None,
) -> UserSearchEvent:
    return UserSearchEvent.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        query=(query or "").strip(),
        filters=filters or {},
        result_count=max(result_count, 0),
        response_ms=response_ms,
    )


def record_click_event(
    *,
    user,
    job_id: int,
    search_event_id: int | None = None,
    rank_position: int | None = None,
    keyword_score: float | None = None,
    semantic_score: float | None = None,
    final_score: float | None = None,
) -> JobClickEvent:
    job = JobPosting.objects.get(pk=job_id)
    search_event = None
    if search_event_id:
        search_event = UserSearchEvent.objects.filter(pk=search_event_id).first()

    return JobClickEvent.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        job=job,
        search_event=search_event,
        rank_position=rank_position if rank_position is not None else 0,
        keyword_score=keyword_score,
        semantic_score=semantic_score,
        final_score=final_score,
    )
