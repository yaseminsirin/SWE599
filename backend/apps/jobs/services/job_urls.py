from urllib.parse import urlparse

_BLOCKED_HOST_SUFFIXES = (".example", ".invalid", ".local", ".test")
_BLOCKED_HOSTS = frozenset(
    {
        "demo.jobsense.example",
    }
)


def resolve_external_job_url(raw: str | None) -> str | None:
    """Return a safe external listing URL, or None if missing or placeholder."""
    url = (raw or "").strip()
    if not url.startswith(("http://", "https://")):
        return None

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    if host in _BLOCKED_HOSTS:
        return None
    if any(host == suffix[1:] or host.endswith(suffix) for suffix in _BLOCKED_HOST_SUFFIXES):
        return None

    return url
