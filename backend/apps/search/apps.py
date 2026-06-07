import os
import sys

from django.apps import AppConfig


class SearchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.search"

    def ready(self) -> None:
        if "test" in sys.argv or os.environ.get("SKIP_EMBEDDING_WARMUP") == "1":
            return
        from apps.search.services.semantic_search import warmup_embedding_model

        warmup_embedding_model()
