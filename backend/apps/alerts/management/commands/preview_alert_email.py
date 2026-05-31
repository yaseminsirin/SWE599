from django.core.management.base import BaseCommand, CommandError

from apps.alerts.models import JobAlert
from apps.alerts.services.alert_retrieval import retrieve_alert_jobs
from apps.alerts.services.rag.email_generation import (
    build_alert_subject,
    compose_alert_email,
    generate_alert_email_content,
)


class Command(BaseCommand):
    help = "Preview alert email subject, plain text, and HTML without sending."

    def add_arguments(self, parser):
        parser.add_argument("--alert-id", type=int, help="Existing JobAlert id.")
        parser.add_argument(
            "--keyword",
            default="python developer",
            help="Used when --alert-id is omitted (creates a temporary in-memory alert).",
        )
        parser.add_argument("--max-jobs", type=int, default=5)

    def handle(self, *args, **options):
        alert = None
        if options["alert_id"]:
            alert = JobAlert.objects.filter(pk=options["alert_id"]).first()
            if alert is None:
                raise CommandError(f"JobAlert id={options['alert_id']} not found.")

        if alert is None:
            alert = JobAlert(
                keyword=options["keyword"],
                is_active=True,
                notify_email="preview@example.com",
                is_remote=True,
            )

        jobs = retrieve_alert_jobs(alert, min_results=1, max_results=options["max_jobs"])
        if not jobs and alert.pk:
            from apps.jobs.models import JobPosting

            jobs = list(JobPosting.objects.order_by("-posted_at", "-created_at")[: options["max_jobs"]])
        if not jobs:
            raise CommandError("No jobs available for preview.")

        content = generate_alert_email_content(alert, jobs)
        subject = build_alert_subject(alert, len(jobs))
        text_body, html_body = compose_alert_email(content, jobs, alert=alert)

        self.stdout.write(self.style.SUCCESS(f"Subject: {subject}"))
        self.stdout.write(f"used_rag={content.used_rag} provider={content.provider}\n")
        self.stdout.write("--- PLAIN TEXT ---")
        self.stdout.write(text_body)
        self.stdout.write("\n--- HTML (first 2000 chars) ---")
        self.stdout.write(html_body[:2000] + ("..." if len(html_body) > 2000 else ""))
