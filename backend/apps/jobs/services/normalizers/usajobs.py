from typing import Any

from .base import BaseRawNormalizer, build_content_hash, clean_text, parse_datetime, parse_decimal


class USAJobsNormalizer(BaseRawNormalizer):
    source_name = "usajobs"

    def normalize(self, payload: dict[str, Any], *, source_job_id: str) -> dict[str, Any]:
        descriptor = payload.get("MatchedObjectDescriptor", {}) or {}
        position_location = (descriptor.get("PositionLocation") or [{}])[0] or {}
        locations = descriptor.get("PositionLocationDisplay") or ""

        title = clean_text(descriptor.get("PositionTitle"))
        company_name = clean_text(descriptor.get("OrganizationName"))
        description_raw = clean_text((descriptor.get("UserArea") or {}).get("Details", {}).get("JobSummary"))
        description_clean = description_raw
        normalized_title = title.lower()
        location_text = clean_text(locations or position_location.get("LocationName"))

        remuneration = (descriptor.get("PositionRemuneration") or [{}])[0] or {}

        output = self.base_output(source_job_id=source_job_id, payload=payload)
        output.update(
            {
                "title": title,
                "normalized_title": normalized_title,
                "company_name": company_name,
                "description_raw": description_raw,
                "description_clean": description_clean,
                "job_url": descriptor.get("PositionURI") or "",
                "location_text": location_text,
                "city": clean_text(position_location.get("CityName")),
                "country": clean_text(position_location.get("CountryCode")),
                "is_remote": bool(descriptor.get("PositionLocationWithinArea")),
                "employment_type": clean_text(descriptor.get("PositionSchedule") or ""),
                "posted_at": parse_datetime(descriptor.get("PublicationStartDate")),
                "expires_at": parse_datetime(descriptor.get("ApplicationCloseDate")),
                "salary_min": parse_decimal(remuneration.get("MinimumRange")),
                "salary_max": parse_decimal(remuneration.get("MaximumRange")),
                "salary_currency": clean_text(remuneration.get("RateIntervalCode") or "USD"),
                "salary_period": clean_text(remuneration.get("RateIntervalCode")),
                "category_raw": clean_text(descriptor.get("JobCategory") or ""),
                "category_normalized": clean_text(descriptor.get("JobCategory") or "").lower(),
            }
        )
        output["content_hash"] = build_content_hash(
            normalized_title=normalized_title,
            company_name=company_name,
            location_text=location_text,
            description_clean=description_clean,
        )
        return output
