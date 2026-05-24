import os

from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask


class Command(BaseCommand):
    help = "Register or update nightly ingest and alert schedules in django-celery-beat."

    def handle(self, *args, **options):
        timezone = os.getenv("INGEST_SCHEDULE_TIMEZONE", "Europe/Istanbul")

        ingest_hour = int(os.getenv("INGEST_SCHEDULE_HOUR", "3"))
        ingest_minute = int(os.getenv("INGEST_SCHEDULE_MINUTE", "0"))
        alert_hour = int(
            os.getenv(
                "ALERT_SCHEDULE_HOUR",
                str(ingest_hour + 1 if ingest_hour < 23 else 0),
            )
        )
        alert_minute = int(os.getenv("ALERT_SCHEDULE_MINUTE", "0"))

        ingest_schedule, _ = CrontabSchedule.objects.get_or_create(
            minute=str(ingest_minute),
            hour=str(ingest_hour),
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            timezone=timezone,
        )
        alert_schedule, _ = CrontabSchedule.objects.get_or_create(
            minute=str(alert_minute),
            hour=str(alert_hour),
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            timezone=timezone,
        )

        ingest_task, ingest_created = PeriodicTask.objects.update_or_create(
            name="nightly-job-refresh",
            defaults={
                "task": "apps.jobs.tasks.nightly_job_refresh_task",
                "crontab": ingest_schedule,
                "enabled": True,
                "description": "Fetch max jobs per source, prune stale, normalize, embed.",
            },
        )
        alert_task, alert_created = PeriodicTask.objects.update_or_create(
            name="nightly-job-alerts",
            defaults={
                "task": "apps.alerts.tasks.process_job_alerts_task",
                "crontab": alert_schedule,
                "enabled": True,
                "description": "Send nightly job alert emails (semantic retrieval + RAG copy).",
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if ingest_created else 'Updated'} ingest schedule: "
                f"{ingest_hour:02d}:{ingest_minute:02d} {timezone} (task id={ingest_task.id})"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if alert_created else 'Updated'} alert schedule: "
                f"{alert_hour:02d}:{alert_minute:02d} {timezone} (task id={alert_task.id})"
            )
        )
