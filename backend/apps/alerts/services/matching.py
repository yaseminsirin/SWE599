import logging

from django.conf import settings
from django.utils import timezone

from apps.jobs.models import JobPosting

from ..models import AlertDeliveryLog, JobAlert
from .alert_retrieval import retrieve_alert_jobs
from .brevo_email import send_transactional_email
from .rag.email_generation import (
    build_alert_subject,
    compose_alert_email,
    generate_alert_email_content,
)

logger = logging.getLogger(__name__)


def _alert_recipient(alert: JobAlert) -> str:
    return (alert.notify_email or "").strip() or getattr(settings, "ALERT_DEFAULT_EMAIL", "")


def _send_alert_email(alert: JobAlert, jobs: list[JobPosting], *, recipient: str) -> dict:
    email_content = generate_alert_email_content(alert, jobs)
    subject = build_alert_subject(alert, len(jobs))
    text_body, html_body = compose_alert_email(email_content, jobs, alert=alert)
    try:
        send_transactional_email(
            recipient=recipient,
            subject=subject,
            body=text_body,
            html_body=html_body,
        )
    except Exception as exc:
        logger.exception(
            "Alert email delivery failed for alert %s to %s: %s",
            alert.id,
            recipient,
            exc,
        )
        raise
    return {
        "used_rag": email_content.used_rag,
        "provider": email_content.provider,
    }


def process_job_alerts(
    *,
    min_results_per_alert: int = 10,
    max_results_per_alert: int = 20,
) -> dict:
    summary = {
        "alerts_seen": 0,
        "alerts_notified": 0,
        "jobs_matched": 0,
        "deliveries_created": 0,
        "delivery_duplicates": 0,
        "rag_emails": 0,
        "fallback_emails": 0,
        "errors": [],
    }

    max_results_per_alert = max(1, min(max_results_per_alert, 20))
    min_results_per_alert = max(1, min(min_results_per_alert, max_results_per_alert))

    alerts = JobAlert.objects.filter(is_active=True)
    for alert in alerts:
        summary["alerts_seen"] += 1
        recipient = _alert_recipient(alert)
        if not recipient:
            continue

        try:
            candidates = retrieve_alert_jobs(
                alert,
                min_results=min_results_per_alert,
                max_results=max_results_per_alert,
            )
            if not candidates:
                continue

            jobs_to_send: list[JobPosting] = []
            for job in candidates:
                delivery, created = AlertDeliveryLog.objects.get_or_create(
                    alert=alert,
                    job=job,
                )
                if created:
                    summary["deliveries_created"] += 1
                    jobs_to_send.append(job)
                else:
                    summary["delivery_duplicates"] += 1

            if jobs_to_send:
                email_meta = _send_alert_email(alert, jobs_to_send, recipient=recipient)
                if email_meta.get("used_rag"):
                    summary["rag_emails"] += 1
                else:
                    summary["fallback_emails"] += 1
                alert.last_notified_at = timezone.now()
                alert.save(update_fields=["last_notified_at", "updated_at"])
                summary["alerts_notified"] += 1
                summary["jobs_matched"] += len(jobs_to_send)
        except Exception as exc:
            summary["errors"].append(
                {
                    "alert_id": alert.id,
                    "error": str(exc),
                }
            )

    return summary
