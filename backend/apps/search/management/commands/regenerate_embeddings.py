from django.core.management.base import BaseCommand

from apps.search.services.embedding_generation import regenerate_job_embeddings


class Command(BaseCommand):
    help = (
        "Generate local sentence-transformer embeddings incrementally. "
        "Default: missing jobs only, priority remotive → adzuna → usajobs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default="",
            help="Only jobs from this source (remotive, adzuna, usajobs).",
        )
        parser.add_argument(
            "--tech-only",
            action="store_true",
            help="Limit to tech-related searchable jobs (recommended for demo).",
        )
        parser.add_argument(
            "--relevant-only",
            action="store_true",
            help="Alias for --tech-only (demo-relevant tech jobs for semantic search).",
        )
        parser.add_argument(
            "--all-jobs",
            action="store_true",
            help="Include non-tech jobs (overrides --tech-only and EMBEDDING_TECH_ONLY).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Max jobs to embed this run (also EMBEDDING_MAX_JOBS_PER_RUN).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=None,
            help="ORM iterator chunk size (default EMBEDDING_BATCH_SIZE).",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=None,
            help="Seconds to sleep between jobs (default EMBEDDING_SLEEP_SECONDS).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Replace existing embeddings for selected jobs (does not delete JobPosting).",
        )
        parser.add_argument(
            "--include-existing",
            action="store_true",
            help="Re-attempt jobs that already have an active-provider embedding.",
        )

    def handle(self, *args, **options):
        source = (options.get("source") or "").strip() or None
        if options.get("all_jobs"):
            tech_only = False
        elif options.get("tech_only") or options.get("relevant_only"):
            tech_only = True
        else:
            tech_only = None

        summary = regenerate_job_embeddings(
            source=source,
            tech_only=tech_only,
            limit=options.get("limit"),
            batch_size=options.get("batch_size"),
            sleep_seconds=options.get("sleep"),
            missing_only=not options.get("include_existing"),
            force=options.get("force"),
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Candidates {summary['candidates']}; "
                f"embedded {summary['regenerated']}; "
                f"errors {summary['errors']}; "
                f"stopped_on_quota={summary['stopped_on_quota']}"
            )
        )
        if summary.get("last_error"):
            self.stdout.write(self.style.WARNING(f"Last error: {summary['last_error']}"))
        if summary.get("fallback"):
            self.stdout.write(
                self.style.ERROR(
                    f"WARNING: {summary['fallback']} fallback embeddings written. "
                    "Use EMBEDDING_STRICT_PROVIDER=true and sentence_transformers provider."
                )
            )
