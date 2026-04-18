import hashlib
import re
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.utils import timezone


def clean_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def build_content_hash(
    *,
    normalized_title: str,
    company_name: str,
    location_text: str,
    description_clean: str,
) -> str:
    normalized = "|".join(
        [
            clean_text(normalized_title).lower(),
            clean_text(company_name).lower(),
            clean_text(location_text).lower(),
            clean_text(description_clean).lower(),
        ]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class BaseRawNormalizer(ABC):
    source_name = ""

    @abstractmethod
    def normalize(self, payload: dict[str, Any], *, source_job_id: str) -> dict[str, Any]:
        """Map source payload into JobPosting fields."""

    def base_output(self, *, source_job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": self.source_name,
            "source_job_id": source_job_id,
            "description_raw": clean_text(payload.get("description", "")),
            "fetched_at": timezone.now(),
            "normalized_at": timezone.now(),
        }
