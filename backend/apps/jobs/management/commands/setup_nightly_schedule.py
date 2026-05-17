import os

from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask


class Command(BaseCommand):
    help = "Register or update the nightly job refresh schedule in django-celery-beat."

    def handle(self, *args, **options):
        hour = int(os.getenv("INGEST_SCHEDULE_HOUR", "3"))
        minute = int(os.getenv("INGEST_SCHEDULE_MINUTE", "0"))
        timezone = os.getenv("INGEST_SCHEDULE_TIMEZONE", "Europe/Istanbul")

        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute=str(minute),
            hour=str(hour),
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            timezone=timezone,
        )

        task, created = PeriodicTask.objects.update_or_create(
            name="nightly-job-refresh",
            defaults={
                "task": "apps.jobs.tasks.nightly_job_refresh_task",
                "crontab": schedule,
                "enabled": True,
                "description": "Fetch max jobs per source, prune stale, normalize, embed.",
            },
        )

        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} nightly schedule: {hour:02d}:{minute:02d} {timezone} "
                f"(task id={task.id})"
            )
        )
