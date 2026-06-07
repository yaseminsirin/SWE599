import os
import sys
import threading

from django.apps import AppConfig


class SearchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.search"

    def ready(self) -> None:
        if "test" in sys.argv:
            return
        if os.environ.get("SKIP_EMBEDDING_WARMUP") == "1":
            return
        # Only the web container should warm the model; worker/beat load lazily on task.
        if os.environ.get("EMBEDDING_WARMUP_ON_START") != "1":
            return

        from apps.search.services.semantic_search import warmup_embedding_model

        threading.Thread(target=warmup_embedding_model, daemon=True).start()
