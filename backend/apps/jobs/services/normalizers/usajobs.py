from typing import Any

from apps.jobs.services.job_labels import (
    category_label_from_raw,
    employment_label_from_raw,
    infer_is_remote,
    normalize_employment_slug,
)

from .base import (
    BaseRawNormalizer,
    build_content_hash,
    clean_text,
    parse_datetime,
    parse_decimal,
    truncate_text,
)


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
        schedule_raw = descriptor.get("PositionSchedule") or descriptor.get("PositionOfferingType")
        employment_label = employment_label_from_raw(schedule_raw)
        employment_slug = normalize_employment_slug(schedule_raw) or normalize_employment_slug(employment_label)

        category_label = category_label_from_raw(descriptor.get("JobCategory"))
        telework = clean_text(descriptor.get("TeleworkIndicator") or "")
        is_remote = infer_is_remote(
            is_remote=telework.lower() in {"yes", "true", "1"},
            source=self.source_name,
            title=title,
            description=description_clean,
            location=location_text,
            employment_slug=employment_slug,
        )

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
                "is_remote": is_remote,
                "employment_type": employment_slug,
                "posted_at": parse_datetime(descriptor.get("PublicationStartDate")),
                "expires_at": parse_datetime(descriptor.get("ApplicationCloseDate")),
                "salary_min": parse_decimal(remuneration.get("MinimumRange")),
                "salary_max": parse_decimal(remuneration.get("MaximumRange")),
                "salary_currency": "USD",
                "salary_period": clean_text(remuneration.get("RateIntervalCode") or ""),
                "category_raw": truncate_text(category_label, 120),
                "category_normalized": truncate_text(category_label, 120).lower(),
            }
        )
        output["content_hash"] = build_content_hash(
            normalized_title=normalized_title,
            company_name=company_name,
            location_text=location_text,
            description_clean=description_clean,
        )
        return output
