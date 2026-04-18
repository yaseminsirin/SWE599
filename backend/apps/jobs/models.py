from django.db import models
from django.utils import timezone


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class RawJobRecord(TimestampedModel):
    source = models.CharField(max_length=50, db_index=True)
    source_job_id = models.CharField(max_length=255, db_index=True)
    payload = models.JSONField()
    normalized_job = models.ForeignKey(
        "JobPosting",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="raw_records",
    )
    fetched_at = models.DateTimeField(default=timezone.now, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["source", "source_job_id"]),
            models.Index(fields=["source", "fetched_at"]),
        ]
        ordering = ["-fetched_at"]

    def __str__(self) -> str:
        return f"{self.source}:{self.source_job_id}"


class JobPosting(TimestampedModel):
    source = models.CharField(max_length=50, db_index=True)
    source_job_id = models.CharField(max_length=255, db_index=True)
    raw_record = models.ForeignKey(
        RawJobRecord,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="job_postings",
    )

    title = models.CharField(max_length=255, db_index=True)
    normalized_title = models.CharField(max_length=255, blank=True, db_index=True)
    company_name = models.CharField(max_length=255, blank=True, db_index=True)
    description_raw = models.TextField(blank=True)
    description_clean = models.TextField(blank=True)
    job_url = models.URLField(max_length=2000)

    location_text = models.CharField(max_length=255, blank=True, db_index=True)
    city = models.CharField(max_length=120, blank=True, db_index=True)
    country = models.CharField(max_length=120, blank=True, db_index=True)
    is_remote = models.BooleanField(default=False, db_index=True)
    employment_type = models.CharField(max_length=50, blank=True, db_index=True)

    posted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    salary_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_currency = models.CharField(max_length=8, blank=True, db_index=True)
    salary_period = models.CharField(max_length=32, blank=True, db_index=True)

    category_raw = models.CharField(max_length=120, blank=True)
    category_normalized = models.CharField(max_length=120, blank=True, db_index=True)

    content_hash = models.CharField(max_length=64, unique=True)
    fetched_at = models.DateTimeField(default=timezone.now, db_index=True)
    normalized_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["source", "source_job_id"]),
            models.Index(fields=["is_remote", "employment_type"]),
            models.Index(fields=["country", "city"]),
            models.Index(fields=["-posted_at"]),
        ]
        ordering = ["-posted_at", "-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.company_name})"
