from celery import shared_task

from .services.matching import process_job_alerts


@shared_task
def process_job_alerts_task(
    *,
    min_results_per_alert: int = 10,
    max_results_per_alert: int = 20,
) -> dict:
    return process_job_alerts(
        min_results_per_alert=min_results_per_alert,
        max_results_per_alert=max_results_per_alert,
    )
