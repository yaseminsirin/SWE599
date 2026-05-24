from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count, Max

from apps.jobs.models import JobPosting
from apps.search.models import JobEmbedding
from apps.search.services.embeddings.factory import FALLBACK_MODEL_NAME, get_embedding_provider
from apps.search.services.job_quality import REAL_JOB_SOURCES, get_searchable_job_queryset


class Command(BaseCommand):
    help = "Audit JobEmbedding coverage, tech gaps, source breakdown, and mixed-space risk."

    def handle(self, *args, **options):
        configured = settings.EMBEDDING_PROVIDER
        strict = getattr(settings, "EMBEDDING_STRICT_PROVIDER", False)
        active = get_embedding_provider()

        self.stdout.write("=== Embedding configuration ===")
        self.stdout.write(f"  EMBEDDING_PROVIDER={configured}")
        self.stdout.write(f"  EMBEDDING_MODEL_NAME={settings.EMBEDDING_MODEL_NAME}")
        self.stdout.write(f"  EMBEDDING_DIMENSION={settings.EMBEDDING_DIMENSION}")
        self.stdout.write(f"  EMBEDDING_STRICT_PROVIDER={strict}")
        self.stdout.write(f"  EMBEDDING_BATCH_SIZE={getattr(settings, 'EMBEDDING_BATCH_SIZE', 50)}")
        self.stdout.write(
            f"  EMBEDDING_MAX_JOBS_PER_RUN={getattr(settings, 'EMBEDDING_MAX_JOBS_PER_RUN', 0)}"
        )
        self.stdout.write(
            f"  EMBEDDING_SLEEP_SECONDS={getattr(settings, 'EMBEDDING_SLEEP_SECONDS', 0.0)}"
        )
        self.stdout.write(
            f"  EMBEDDING_SOURCE_FILTER={getattr(settings, 'EMBEDDING_SOURCE_FILTER', '') or '(none)'}"
        )
        self.stdout.write(f"  EMBEDDING_TECH_ONLY={getattr(settings, 'EMBEDDING_TECH_ONLY', None)}")
        self.stdout.write(f"  SEMANTIC_TECH_ONLY={getattr(settings, 'SEMANTIC_TECH_ONLY', True)}")
        self.stdout.write(f"  Active provider: {active.provider_name}/{active.model_name}")
        self.stdout.write(
            f"  GEMINI_API_KEY configured: {bool(getattr(settings, 'GEMINI_API_KEY', '').strip())}"
        )

        self.stdout.write("\n=== JobPosting totals (real API sources) ===")
        real_qs = JobPosting.objects.filter(source__in=REAL_JOB_SOURCES)
        real_total = real_qs.count()
        self.stdout.write(f"  Total real jobs: {real_total}")
        for row in real_qs.values("source").annotate(n=Count("id")).order_by("-n"):
            self.stdout.write(f"    {row['source']}: {row['n']}")

        searchable_all = get_searchable_job_queryset(
            real_sources_only=True,
            exclude_demo=True,
            tech_only=False,
        )
        searchable_tech = get_searchable_job_queryset(
            real_sources_only=True,
            exclude_demo=True,
            tech_only=True,
        )
        searchable_all_count = searchable_all.count()
        searchable_tech_count = searchable_tech.count()

        self.stdout.write("\n=== Searchable scope ===")
        self.stdout.write(f"  Quality-filtered (all): {searchable_all_count}")
        self.stdout.write(f"  Tech-related (SEMANTIC_TECH_ONLY): {searchable_tech_count}")
        self.stdout.write(
            f"  Non-tech searchable: {max(searchable_all_count - searchable_tech_count, 0)}"
        )

        self.stdout.write("\n=== JobEmbedding rows by provider/model ===")
        rows = (
            JobEmbedding.objects.values("provider", "model_name")
            .annotate(n=Count("id"))
            .order_by("-n")
        )
        embed_total = 0
        for row in rows:
            embed_total += row["n"]
            self.stdout.write(f"  {row['provider']}/{row['model_name']}: {row['n']}")
        self.stdout.write(f"  Total embedding rows: {embed_total}")

        active_embedded = JobEmbedding.objects.filter(
            provider=active.provider_name,
            model_name=active.model_name,
            job__source__in=REAL_JOB_SOURCES,
        )
        active_count = active_embedded.count()
        missing_all = searchable_all_count - searchable_all.filter(
            embeddings__provider=active.provider_name,
            embeddings__model_name=active.model_name,
        ).count()
        missing_tech = searchable_tech_count - searchable_tech.filter(
            embeddings__provider=active.provider_name,
            embeddings__model_name=active.model_name,
        ).count()

        last_created = JobEmbedding.objects.aggregate(last=Max("created_at"))["last"]
        last_updated = JobEmbedding.objects.aggregate(last=Max("updated_at"))["last"]

        self.stdout.write("\n=== Active index coverage ===")
        self.stdout.write(
            f"  Embedded ({active.provider_name}/{active.model_name}): {active_count}"
        )
        self.stdout.write(f"  Missing (all searchable): {missing_all}")
        self.stdout.write(f"  Missing (tech searchable): {missing_tech}")
        self.stdout.write(f"  Last embedding created: {last_created or '—'}")
        self.stdout.write(f"  Last embedding updated: {last_updated or '—'}")

        gemini_rows = JobEmbedding.objects.filter(provider="gemini").count()
        hash_rows = JobEmbedding.objects.filter(
            provider="local",
            model_name=FALLBACK_MODEL_NAME,
        ).count()
        legacy_rows = JobEmbedding.objects.exclude(
            provider=active.provider_name,
            model_name=active.model_name,
        ).count()

        self.stdout.write("\n=== By source (active provider) ===")
        for source in REAL_JOB_SOURCES:
            src_total = searchable_all.filter(source=source).count()
            src_tech = searchable_tech.filter(source=source).count()
            src_embedded = active_embedded.filter(job__source=source).count()
            src_missing_tech = src_tech - searchable_tech.filter(
                source=source,
                embeddings__provider=active.provider_name,
                embeddings__model_name=active.model_name,
            ).count()
            self.stdout.write(
                f"  {source}: total={src_total} tech={src_tech} "
                f"embedded={src_embedded} missing_tech={src_missing_tech}"
            )

        self.stdout.write("\n=== Demo target estimate ===")
        self.stdout.write(
            f"  For semantic search with SEMANTIC_TECH_ONLY=true, aim for "
            f"{searchable_tech_count} tech embeddings (currently {searchable_tech_count - missing_tech})."
        )

        self.stdout.write("\n=== Mixed-space / legacy index risk ===")
        if legacy_rows:
            self.stdout.write(
                self.style.WARNING(
                    f"  {legacy_rows} legacy embedding rows (non-active provider/model) in DB."
                )
            )
        if gemini_rows:
            self.stdout.write(
                self.style.WARNING(
                    f"  {gemini_rows} legacy Gemini rows (768-dim era) — not used by active index."
                )
            )
        if hash_rows:
            self.stdout.write(
                self.style.ERROR(
                    f"  {hash_rows} local hash fallback rows — incompatible with sentence-transformers."
                )
            )
        if active_count and not hash_rows:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Active index: {active.provider_name}/{active.model_name} "
                    f"({settings.EMBEDDING_DIMENSION}-dim), {active_count} vectors."
                )
            )
        elif not active_count:
            self.stdout.write("  No active-provider embeddings yet — run regenerate_embeddings.")

        if strict:
            self.stdout.write(self.style.SUCCESS("\nStrict provider mode: ON"))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "\nStrict provider mode: OFF — enable EMBEDDING_STRICT_PROVIDER=true for demo."
                )
            )
