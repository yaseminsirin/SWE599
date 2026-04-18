import os
from typing import Any

from django.utils import timezone

from .base import BaseJobSourceAdapter


class AdzunaAdapter(BaseJobSourceAdapter):
    source_name = "adzuna"
    base_url_env = "ADZUNA_BASE_URL"
    default_country = "us"

    def fetch_jobs(self, *, page: int = 1, per_page: int | None = None) -> list[dict[str, Any]]:
        app_id = os.getenv("ADZUNA_APP_ID", "")
        app_key = os.getenv("ADZUNA_APP_KEY", "")
        country = os.getenv("ADZUNA_COUNTRY", self.default_country)
        page_size = per_page or self.page_size

        if not app_id or not app_key:
            raise ValueError("ADZUNA_APP_ID and ADZUNA_APP_KEY must be configured")

        payload = self._request_json(
            f"{country}/search/{page}",
            params={
                "app_id": app_id,
                "app_key": app_key,
                "results_per_page": page_size,
            },
        )
        results = payload.get("results", [])
        return [self.map_to_raw(item) for item in results]

    def map_to_raw(self, item: dict[str, Any]) -> dict[str, Any]:
        source_job_id = str(item.get("id") or item.get("adref") or "")
        if not source_job_id:
            raise ValueError("Adzuna job item missing id")

        return {
            "source": self.source_name,
            "source_job_id": source_job_id,
            "payload": item,
            "fetched_at": timezone.now(),
        }
