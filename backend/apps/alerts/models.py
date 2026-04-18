from django.conf import settings
from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class JobAlert(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="job_alerts",
    )
    name = models.CharField(max_length=120, blank=True)
    keyword = models.CharField(max_length=255, blank=True, db_index=True)
    location_text = models.CharField(max_length=255, blank=True, db_index=True)
    is_remote = models.BooleanField(null=True, blank=True, db_index=True)
    employment_type = models.CharField(max_length=50, blank=True, db_index=True)
    filters = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    last_notified_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self) -> str:
        return self.name or f"Alert:{self.user_id}:{self.keyword}"


class AlertDeliveryLog(TimestampedModel):
    alert = models.ForeignKey(
        JobAlert,
        on_delete=models.CASCADE,
        related_name="delivery_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alert_delivery_logs",
    )
    job = models.ForeignKey(
        "jobs.JobPosting",
        on_delete=models.CASCADE,
        related_name="alert_delivery_logs",
    )
    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        unique_together = ("alert", "job")
        indexes = [
            models.Index(fields=["user", "-sent_at"]),
            models.Index(fields=["alert", "-sent_at"]),
        ]

    def __str__(self) -> str:
        return f"AlertDelivery:{self.alert_id}:{self.job_id}"
