from django.conf import settings
from django.core.management.base import BaseCommand

from apps.jobs.services.demo_dataset import DEMO_SOURCE
from apps.jobs.services.demo_seed import clear_demo_jobs, isolate_demo_embeddings, seed_demo_jobs
from apps.search.services.embedding_generation import generate_job_embedding
from apps.search.services.embeddings.factory import get_embedding_provider

from apps.jobs.models import JobPosting


class Command(BaseCommand):
    help = (
        "OPTIONAL dev/test only — seed fake demo jobs (source=demo). "
        "Do NOT use for final presentation; use real Adzuna/USAJOBS/Remotive ingestion instead."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing demo jobs before seeding (same as --clear-demo).",
        )
        parser.add_argument(
            "--clear-demo",
            action="store_true",
            help="Only remove demo jobs; do not create new ones.",
        )
        parser.add_argument(
            "--embed",
            action="store_true",
            help="Generate Gemini/local embeddings for demo jobs after seeding.",
        )
        parser.add_argument(
            "--isolate-embeddings",
            action="store_true",
            help="Remove embeddings for non-demo jobs so semantic search highlights demo data.",
        )

    def handle(self, *args, **options):
        if options["clear_demo"]:
            summary = clear_demo_jobs()
            self.stdout.write(self.style.WARNING(f"Cleared demo data: {summary}"))
            return

        summary = seed_demo_jobs(reset=options["reset"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo seed complete (source={DEMO_SOURCE}): {summary['demo_jobs_total']} jobs "
                f"({summary['demo_jobs_created']} newly created)."
            )
        )

        if options["isolate_embeddings"]:
            provider = get_embedding_provider()
            removed = isolate_demo_embeddings(
                provider_name=provider.provider_name,
                model_name=provider.model_name,
            )
            self.stdout.write(
                self.style.WARNING(
                    f"Removed {removed} non-demo embeddings for "
                    f"{provider.provider_name}/{provider.model_name}."
                )
            )

        if options["embed"]:
            provider = get_embedding_provider()
            jobs = JobPosting.objects.filter(source=DEMO_SOURCE).order_by("id")
            ok = 0
            errors = 0
            for job in jobs.iterator():
                try:
                    generate_job_embedding(job, force=True)
                    ok += 1
                except Exception as exc:
                    errors += 1
                    self.stderr.write(f"Embedding failed for {job.source_job_id}: {exc}")
            self.stdout.write(
                self.style.SUCCESS(
                    f"Embedded {ok} demo jobs ({errors} errors). "
                    f"Provider={provider.provider_name} model={provider.model_name} "
                    f"dim={settings.EMBEDDING_DIMENSION}"
                )
            )
