from typing import Any

from .adapters import AdzunaAdapter, RemotiveAdapter, USAJobsAdapter

ADAPTERS = {
    "adzuna": AdzunaAdapter,
    "usajobs": USAJobsAdapter,
    "remotive": RemotiveAdapter,
}


def fetch_source_page(source: str, *, page: int = 1, per_page: int = 50) -> list[dict[str, Any]]:
    adapter_cls = ADAPTERS.get(source)
    if adapter_cls is None:
        raise ValueError(f"Unsupported source: {source}")
    adapter = adapter_cls()
    return adapter.fetch_jobs(page=page, per_page=per_page)


def fetch_all_sources_page(*, page: int = 1, per_page: int = 50) -> dict[str, list[dict[str, Any]]]:
    results: dict[str, list[dict[str, Any]]] = {}
    for source, adapter_cls in ADAPTERS.items():
        adapter = adapter_cls()
        results[source] = adapter.fetch_jobs(page=page, per_page=per_page)
    return results
