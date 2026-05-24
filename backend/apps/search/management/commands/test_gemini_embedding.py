from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.search.services.embeddings.factory import embed_text, get_embedding_provider
from apps.search.services.embeddings.providers.gemini import GeminiEmbeddingProvider


class Command(BaseCommand):
    help = "Test Gemini embedding API only (no job ingest or alert processing)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--text",
            default="python backend developer remote",
            help="Sample text to embed",
        )

    def handle(self, *args, **options):
        if settings.EMBEDDING_PROVIDER != "gemini":
            raise CommandError(
                "Set EMBEDDING_PROVIDER=gemini in .env before running this command."
            )

        provider = get_embedding_provider()
        if not isinstance(provider, GeminiEmbeddingProvider):
            raise CommandError(
                "Gemini provider not active (check GEMINI_API_KEY). "
                f"Active provider: {provider.provider_name}"
            )

        text = options["text"]
        self.stdout.write(
            f"Model: {provider.model_name} | dimension: {provider.vector_dimension}"
        )

        query_vec = embed_text(text, task_type="RETRIEVAL_QUERY")
        doc_vec = embed_text(text, task_type="RETRIEVAL_DOCUMENT")

        self.stdout.write(self.style.SUCCESS(f"RETRIEVAL_QUERY vector length: {len(query_vec)}"))
        self.stdout.write(self.style.SUCCESS(f"RETRIEVAL_DOCUMENT vector length: {len(doc_vec)}"))
        self.stdout.write(f"First 5 values (query): {query_vec[:5]}")
