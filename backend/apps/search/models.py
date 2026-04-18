from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class JobEmbedding(TimestampedModel):
    job = models.ForeignKey(
        "jobs.JobPosting",
        on_delete=models.CASCADE,
        related_name="embeddings",
    )
    provider = models.CharField(max_length=64, db_index=True)
    model_name = models.CharField(max_length=128, db_index=True)
    vector_dimension = models.PositiveIntegerField()
    embedding = models.JSONField()

    class Meta:
        unique_together = ("job", "provider", "model_name")
        indexes = [
            models.Index(fields=["provider", "model_name"]),
        ]

    def __str__(self) -> str:
        return f"{self.job_id}:{self.provider}:{self.model_name}"
