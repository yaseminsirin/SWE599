from django.core.mail import send_mail
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.jobs.models import JobPosting

from ..models import AlertDeliveryLog, JobAlert


def _match_alert_jobs(alert: JobAlert) -> QuerySet[JobPosting]:
    queryset = JobPosting.objects.all().order_by("-posted_at", "-created_at")

    if alert.last_notified_at:
        queryset = queryset.filter(normalized_at__gt=alert.last_notified_at)

    if alert.keyword:
        queryset = queryset.filter(
            Q(title__icontains=alert.keyword) | Q(description_clean__icontains=alert.keyword)
        )

    if alert.location_text:
        queryset = queryset.filter(
            Q(city__icontains=alert.location_text)
            | Q(country__icontains=alert.location_text)
            | Q(location_text__icontains=alert.location_text)
        )

    if alert.is_remote is not None:
        queryset = queryset.filter(is_remote=alert.is_remote)

    if alert.employment_type:
        queryset = queryset.filter(employment_type__iexact=alert.employment_type)

    return queryset


def _send_alert_email(alert: JobAlert, jobs: list[JobPosting]) -> None:
    subject = f"Job alert: {alert.name or alert.keyword or 'New matches'}"
    lines = ["Here are your latest matching jobs:", ""]
    for job in jobs:
        lines.append(f"- {job.title} | {job.company_name} | {job.job_url}")
    body = "\n".join(lines)
    send_mail(
        subject=subject,
        message=body,
        from_email=None,
        recipient_list=[alert.user.email],
        fail_silently=False,
    )


def process_job_alerts(*, max_results_per_alert: int = 20) -> dict:
    summary = {
        "alerts_seen": 0,
        "alerts_notified": 0,
        "jobs_matched": 0,
        "deliveries_created": 0,
        "delivery_duplicates": 0,
        "errors": [],
    }

    alerts = JobAlert.objects.filter(is_active=True).select_related("user")
    for alert in alerts:
        summary["alerts_seen"] += 1
        if not alert.user.email:
            continue

        try:
            candidates = list(_match_alert_jobs(alert)[:max_results_per_alert])
            if not candidates:
                continue

            jobs_to_send: list[JobPosting] = []
            for job in candidates:
                delivery, created = AlertDeliveryLog.objects.get_or_create(
                    alert=alert,
                    user=alert.user,
                    job=job,
                )
                if created:
                    summary["deliveries_created"] += 1
                    jobs_to_send.append(job)
                else:
                    summary["delivery_duplicates"] += 1

            if jobs_to_send:
                _send_alert_email(alert, jobs_to_send)
                alert.last_notified_at = timezone.now()
                alert.save(update_fields=["last_notified_at", "updated_at"])
                summary["alerts_notified"] += 1
                summary["jobs_matched"] += len(jobs_to_send)
        except Exception as exc:
            summary["errors"].append(
                {
                    "alert_id": alert.id,
                    "user_id": alert.user_id,
                    "error": str(exc),
                }
            )

    return summary
