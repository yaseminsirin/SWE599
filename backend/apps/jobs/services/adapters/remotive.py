from django.utils import timezone

from .base import BaseJobSourceAdapter


class RemotiveAdapter(BaseJobSourceAdapter):
    source_name = "remotive"
    base_url_env = "REMOTIVE_BASE_URL"

    def fetch_jobs(self, *, page: int = 1, per_page: int | None = None) -> list[dict[str, object]]:
        page_size = per_page or self.page_size
        offset = max(page - 1, 0) * page_size

        payload = self._request_json(
            "remote-jobs",
            params={
                "limit": page_size,
                "offset": offset,
            },
        )
        results = payload.get("jobs", [])
        return [self.map_to_raw(item) for item in results]

    def map_to_raw(self, item: dict[str, object]) -> dict[str, object]:
        source_job_id = str(item.get("id") or item.get("url") or "")
        if not source_job_id:
            raise ValueError("Remotive item missing id")

        return {
            "source": self.source_name,
            "source_job_id": source_job_id,
            "payload": item,
            "fetched_at": timezone.now(),
        }
