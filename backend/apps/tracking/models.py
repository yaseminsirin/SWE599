from django.conf import settings
from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserSearchEvent(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="search_events",
    )
    query = models.CharField(max_length=255, db_index=True)
    filters = models.JSONField(default=dict, blank=True)
    result_count = models.PositiveIntegerField(default=0)
    response_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Search:{self.user_id}:{self.query}"


class JobClickEvent(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="click_events",
    )
    job = models.ForeignKey(
        "jobs.JobPosting",
        on_delete=models.CASCADE,
        related_name="click_events",
    )
    search_event = models.ForeignKey(
        UserSearchEvent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="click_events",
    )
    rank_position = models.PositiveIntegerField(db_index=True)
    keyword_score = models.FloatField(null=True, blank=True)
    semantic_score = models.FloatField(null=True, blank=True)
    final_score = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["job", "-created_at"]),
            models.Index(fields=["search_event", "rank_position"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Click:{self.user_id}:{self.job_id}:{self.rank_position}"
