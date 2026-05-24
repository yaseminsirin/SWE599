from django.core.management.base import BaseCommand

from apps.alerts.tasks import process_job_alerts_task


class Command(BaseCommand):
    help = "Process active job alerts now (semantic retrieval + RAG/plain email)."

    def add_arguments(self, parser):
        parser.add_argument("--min", type=int, default=10, dest="min_results")
        parser.add_argument("--max", type=int, default=20, dest="max_results")

    def handle(self, *args, **options):
        summary = process_job_alerts_task(
            min_results_per_alert=options["min_results"],
            max_results_per_alert=options["max_results"],
        )
        self.stdout.write(self.style.SUCCESS(str(summary)))
