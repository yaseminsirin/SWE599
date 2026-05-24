from collections import Counter

from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.jobs.models import JobPosting
from apps.jobs.services.demo_dataset import DEMO_SOURCE
from apps.search.models import JobEmbedding
from apps.search.services.embeddings.factory import get_embedding_provider
from apps.search.services.job_quality import REAL_JOB_SOURCES, is_tech_related_job


class Command(BaseCommand):
    help = "Analyze ingested job counts and noise by source (real API data)."

    def handle(self, *args, **options):
        total = JobPosting.objects.count()
        self.stdout.write(f"Total JobPosting: {total}")

        by_source = JobPosting.objects.values("source").annotate(n=Count("id")).order_by("-n")
        self.stdout.write("\nBy source:")
        for row in by_source:
            self.stdout.write(f"  {row['source']}: {row['n']}")

        demo_count = JobPosting.objects.filter(source=DEMO_SOURCE).count()
        if demo_count:
            self.stdout.write(self.style.WARNING(f"\nDemo jobs present: {demo_count} (excluded from search)"))

        real_qs = JobPosting.objects.filter(source__in=REAL_JOB_SOURCES)
        real_total = real_qs.count()
        tech_total = sum(1 for job in real_qs.iterator() if is_tech_related_job(job))
        self.stdout.write(f"\nReal API jobs: {real_total}")
        self.stdout.write(f"Tech-related (heuristic): {tech_total} ({tech_total / real_total * 100:.1f}%)" if real_total else "")

        provider = get_embedding_provider()
        embedded = JobEmbedding.objects.filter(
            provider=provider.provider_name,
            model_name=provider.model_name,
            job__source__in=REAL_JOB_SOURCES,
        ).count()
        missing = real_total - embedded
        self.stdout.write(
            f"\nEmbeddings ({provider.provider_name}/{provider.model_name}) on real sources: "
            f"{embedded} embedded, {missing} missing"
        )

        title_words = Counter()
        for job in real_qs.iterator():
            for token in (job.title or "").lower().split():
                if len(token) > 3:
                    title_words[token] += 1
        self.stdout.write("\nTop title tokens (real sources):")
        for word, count in title_words.most_common(15):
            self.stdout.write(f"  {word}: {count}")
