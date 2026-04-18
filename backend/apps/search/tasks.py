from celery import shared_task

from .services.embedding_generation import generate_job_embedding
from .services.semantic_search import get_jobs_missing_embeddings


@shared_task
def generate_missing_job_embeddings_task(limit: int = 200) -> dict:
    jobs = get_jobs_missing_embeddings(limit=limit)
    generated = 0
    errors: list[dict] = []

    for job in jobs:
        try:
            generate_job_embedding(job)
            generated += 1
        except Exception as exc:
            errors.append(
                {
                    "job_id": job.id,
                    "error": str(exc),
                }
            )

    return {
        "jobs_seen": len(jobs),
        "embeddings_generated": generated,
        "embedding_errors": errors,
    }
