from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

import requests

from apps.alerts.models import JobAlert
from apps.alerts.services.alert_retrieval import retrieve_alert_jobs
from apps.alerts.services.rag.email_generation import (
    compose_alert_email_body,
    generate_alert_email_content,
)
from apps.alerts.services.rag.job_context import build_alert_query, format_jobs_for_context, parse_llm_response
from apps.alerts.services.rag.llm.factory import get_llm_provider
from apps.alerts.services.rag.llm.ollama_provider import OllamaLLMProvider
from apps.alerts.services.rag.prompts import SYSTEM_PROMPT, build_user_prompt


class Command(BaseCommand):
    help = (
        "Test Ollama RAG email generation only (no email sent, no alert delivery logs). "
        "Verifies Docker → Ollama connectivity and parsed EXPLANATION/HIGHLIGHTS."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--keyword",
            default="python developer",
            help="Alert keyword used for semantic retrieval preview.",
        )
        parser.add_argument(
            "--max-jobs",
            type=int,
            default=5,
            help="Number of retrieved jobs to include in the RAG prompt.",
        )

    def handle(self, *args, **options):
        if (settings.LLM_PROVIDER or "").lower() != "ollama":
            raise CommandError(
                "Set LLM_PROVIDER=ollama in .env before running this command."
            )

        provider = OllamaLLMProvider()
        self.stdout.write(f"Ollama base URL: {provider.base_url}")
        self.stdout.write(f"Ollama model: {provider.model}")

        self._check_connectivity(provider.base_url)

        alert = JobAlert.objects.filter(is_active=True, keyword=options["keyword"]).first()
        if alert is None:
            alert = JobAlert.objects.create(
                keyword=options["keyword"],
                is_active=True,
                notify_email="ollama-test@example.com",
                filters={"search_mode": "semantic"},
            )

        jobs = retrieve_alert_jobs(alert, min_results=1, max_results=options["max_jobs"])
        if not jobs:
            raise CommandError(
                f"No jobs retrieved for keyword={options['keyword']!r}. "
                "Ensure real ingested jobs and embeddings exist."
            )

        self.stdout.write(self.style.SUCCESS(f"\nRetrieved {len(jobs)} job(s):"))
        for job in jobs:
            self.stdout.write(f"  - [{job.id}] {job.title} | {job.company_name}")

        alert_query = build_alert_query(alert)
        jobs_context = format_jobs_for_context(jobs)
        user_prompt = build_user_prompt(
            alert_query=alert_query,
            jobs_context=jobs_context,
            job_count=len(jobs),
        )

        self.stdout.write("\n--- SYSTEM PROMPT ---")
        self.stdout.write(SYSTEM_PROMPT)
        self.stdout.write("\n--- USER PROMPT ---")
        self.stdout.write(user_prompt)

        raw = ""
        parse_error = ""
        try:
            raw = provider.generate(system=SYSTEM_PROMPT, user=user_prompt)
        except Exception as exc:
            parse_error = str(exc)
            self.stdout.write(self.style.ERROR(f"\nOllama generate() failed: {exc}"))

        self.stdout.write("\n--- RAW OLLAMA OUTPUT ---")
        self.stdout.write(raw or "(empty)")

        explanation, highlights = parse_llm_response(raw) if raw else ("", [])
        self.stdout.write("\n--- PARSED EXPLANATION ---")
        self.stdout.write(explanation or "(empty)")
        self.stdout.write("\n--- PARSED HIGHLIGHTS ---")
        if highlights:
            for bullet in highlights:
                self.stdout.write(f"- {bullet}")
        else:
            self.stdout.write("(none)")

        content = generate_alert_email_content(alert, jobs)
        fallback = not content.used_rag
        self.stdout.write(f"\n--- FALLBACK TRIGGERED? {'yes' if fallback else 'no'} ---")
        if fallback and parse_error:
            self.stdout.write(self.style.WARNING(f"Reason: {parse_error}"))
        self.stdout.write(f"used_rag={content.used_rag} provider={content.provider}")

        self.stdout.write("\n--- COMPOSED EMAIL PREVIEW (not sent) ---")
        self.stdout.write(compose_alert_email_body(content, jobs, alert=alert))

    def _check_connectivity(self, base_url: str) -> None:
        self.stdout.write("\nChecking Ollama connectivity from this container...")
        try:
            response = requests.get(f"{base_url}/api/tags", timeout=10)
            response.raise_for_status()
            models = [m.get("name", "") for m in response.json().get("models", [])]
            self.stdout.write(self.style.SUCCESS(f"Reachable: {base_url} ({len(models)} model(s) listed)"))
            if models:
                self.stdout.write("  Models: " + ", ".join(models[:8]))
            llm = get_llm_provider()
            if llm and not llm.is_available():
                raise CommandError("Ollama provider configured but is_available() is False.")
        except requests.RequestException as exc:
            raise CommandError(
                f"Cannot reach Ollama at {base_url} from this container: {exc}\n"
                "Ensure Ollama is running on the host (`ollama serve`) and OLLAMA_BASE_URL=http://host.docker.internal:11434"
            ) from exc
