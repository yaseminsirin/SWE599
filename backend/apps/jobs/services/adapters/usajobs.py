import os
from typing import Any

from django.utils import timezone

from .base import BaseJobSourceAdapter


class USAJobsAdapter(BaseJobSourceAdapter):
    source_name = "usajobs"
    base_url_env = "USAJOBS_BASE_URL"

    def fetch_jobs(self, *, page: int = 1, per_page: int | None = None) -> list[dict[str, Any]]:
        api_key = os.getenv("USAJOBS_API_KEY", "")
        user_agent = os.getenv("USAJOBS_USER_AGENT", "")
        page_size = per_page or self.page_size

        if not api_key or not user_agent:
            raise ValueError("USAJOBS_API_KEY and USAJOBS_USER_AGENT must be configured")

        payload = self._request_json(
            "search",
            params={
                "Page": page,
                "ResultsPerPage": page_size,
            },
            headers={
                "Host": "data.usajobs.gov",
                "User-Agent": user_agent,
                "Authorization-Key": api_key,
            },
        )

        search_result = payload.get("SearchResult", {})
        results = search_result.get("SearchResultItems", [])
        return [self.map_to_raw(item) for item in results]

    def map_to_raw(self, item: dict[str, Any]) -> dict[str, Any]:
        data = item.get("MatchedObjectDescriptor", {})
        source_job_id = str(
            data.get("PositionID")
            or data.get("PositionURI")
            or item.get("MatchedObjectId")
            or ""
        )
        if not source_job_id:
            raise ValueError("USAJOBS item missing position identifier")

        return {
            "source": self.source_name,
            "source_job_id": source_job_id,
            "payload": item,
            "fetched_at": timezone.now(),
        }
