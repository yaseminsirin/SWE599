import os
from abc import ABC, abstractmethod
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class BaseJobSourceAdapter(ABC):
    source_name: str = ""
    base_url_env: str = ""
    timeout_seconds: int = 15
    page_size: int = 50

    def __init__(self) -> None:
        self.base_url = os.getenv(self.base_url_env, "").rstrip("/")
        if not self.base_url:
            raise ValueError(f"{self.base_url_env} is not configured")
        self.session = self._build_session()

    def _build_session(self) -> requests.Session:
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _request_json(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.get(
            url,
            params=params or {},
            headers=headers or {},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    @abstractmethod
    def fetch_jobs(self, *, page: int = 1, per_page: int | None = None) -> list[dict[str, Any]]:
        """Return raw records ready for RawJobRecord storage."""

    @abstractmethod
    def map_to_raw(self, item: dict[str, Any]) -> dict[str, Any]:
        """Map source item to RawJobRecord-like dict."""
