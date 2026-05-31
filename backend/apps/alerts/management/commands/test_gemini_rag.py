from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.alerts.models import JobAlert
from apps.alerts.services.rag.email_generation import compose_alert_email, generate_alert_email_content
from apps.alerts.services.rag.llm.gemini_provider import GeminiLLMProvider
from apps.jobs.models import JobPosting


class Command(BaseCommand):
    help = "Test Gemini RAG email generation only (no alert processing)."

    def handle(self, *args, **options):
        if (settings.LLM_PROVIDER or "").lower() != "gemini":
            raise CommandError("Set LLM_PROVIDER=gemini in .env before running this command.")

        provider = GeminiLLMProvider()
        if not provider.is_available():
            raise CommandError("GEMINI_API_KEY is missing in .env / settings.")

        self.stdout.write(
            f"Gemini model: {provider.model} | key configured: {bool(provider.api_key)}"
        )

        alert = JobAlert.objects.filter(is_active=True).first()
        if alert is None:
            alert = JobAlert.objects.create(
                name="Gemini test alert",
                keyword="python backend",
                is_remote=True,
                is_active=True,
                notify_email="test@example.com",
            )

        jobs = list(JobPosting.objects.order_by("-posted_at", "-created_at")[:5])
        if not jobs:
            raise CommandError("No JobPosting rows in database. Run ingestion first.")

        content = generate_alert_email_content(alert, jobs)
        self.stdout.write(
            self.style.SUCCESS(
                f"used_rag={content.used_rag} provider={content.provider}"
            )
        )
        if not content.used_rag:
            self.stdout.write(
                self.style.WARNING(
                    "Fell back to plain email text. Check logs for Gemini errors."
                )
            )
        text_body, html_body = compose_alert_email(content, jobs, alert=alert)
        self.stdout.write("\n--- PLAIN TEXT ---")
        self.stdout.write(text_body)
        self.stdout.write("\n--- HTML (first 1200 chars) ---")
        self.stdout.write(html_body[:1200] + ("..." if len(html_body) > 1200 else ""))
