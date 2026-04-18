from apps.jobs.models import JobPosting
from apps.search.models import JobEmbedding

from .embeddings.factory import get_embedding_provider


def build_job_embedding_text(job: JobPosting) -> str:
    return "\n".join(
        [
            f"title: {job.title or ''}",
            f"company: {job.company_name or ''}",
            f"location: {job.location_text or ''}",
            f"employment_type: {job.employment_type or ''}",
            f"description: {job.description_clean or ''}",
            f"category: {job.category_normalized or ''}",
        ]
    ).strip()


def generate_job_embedding(job: JobPosting) -> JobEmbedding:
    provider = get_embedding_provider()
    text = build_job_embedding_text(job)
    vector = provider.embed_text(text)
    embedding, _ = JobEmbedding.objects.update_or_create(
        job=job,
        provider=provider.provider_name,
        model_name=provider.model_name,
        defaults={
            "vector_dimension": provider.vector_dimension,
            "embedding": vector,
        },
    )
    return embedding
