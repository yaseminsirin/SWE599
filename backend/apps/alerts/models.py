from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class JobAlert(TimestampedModel):
    name = models.CharField(max_length=120, blank=True)
    keyword = models.CharField(max_length=255, blank=True, db_index=True)
    location_text = models.CharField(max_length=255, blank=True, db_index=True)
    is_remote = models.BooleanField(null=True, blank=True, db_index=True)
    employment_type = models.CharField(max_length=50, blank=True, db_index=True)
    filters = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    notify_email = models.EmailField(blank=True, db_index=True)
    last_notified_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active"], name="alerts_joba_is_acti_idx"),
            models.Index(fields=["-created_at"], name="alerts_joba_created_idx"),
        ]

    def __str__(self) -> str:
        return self.name or f"Alert:{self.keyword}"


class AlertDeliveryLog(TimestampedModel):
    alert = models.ForeignKey(
        JobAlert,
        on_delete=models.CASCADE,
        related_name="delivery_logs",
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
            models.Index(fields=["alert", "-sent_at"], name="alerts_aler_alert_i_eb5d85_idx"),
        ]

    def __str__(self) -> str:
        return f"AlertDelivery:{self.alert_id}:{self.job_id}"
