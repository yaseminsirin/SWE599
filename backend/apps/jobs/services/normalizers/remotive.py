from typing import Any

from apps.jobs.services.job_labels import normalize_employment_slug

from .base import BaseRawNormalizer, build_content_hash, clean_text, parse_datetime, parse_decimal


class RemotiveNormalizer(BaseRawNormalizer):
    source_name = "remotive"

    def normalize(self, payload: dict[str, Any], *, source_job_id: str) -> dict[str, Any]:
        title = clean_text(payload.get("title"))
        company_name = clean_text(payload.get("company_name"))
        description_raw = clean_text(payload.get("description"))
        description_clean = description_raw
        normalized_title = title.lower()
        location_text = clean_text(payload.get("candidate_required_location"))
        category = clean_text(payload.get("category"))
        employment_slug = normalize_employment_slug(payload.get("job_type"))

        output = self.base_output(source_job_id=source_job_id, payload=payload)
        output.update(
            {
                "title": title,
                "normalized_title": normalized_title,
                "company_name": company_name,
                "description_raw": description_raw,
                "description_clean": description_clean,
                "job_url": payload.get("url") or "",
                "location_text": location_text,
                "city": "",
                "country": "",
                "is_remote": True,
                "employment_type": employment_slug or "contract",
                "posted_at": parse_datetime(payload.get("publication_date")),
                "expires_at": None,
                "salary_min": parse_decimal(payload.get("salary_min")),
                "salary_max": parse_decimal(payload.get("salary_max")),
                "salary_currency": clean_text(payload.get("salary_currency")),
                "salary_period": "",
                "category_raw": category,
                "category_normalized": category.lower(),
            }
        )
        output["content_hash"] = build_content_hash(
            normalized_title=normalized_title,
            company_name=company_name,
            location_text=location_text,
            description_clean=description_clean,
        )
        return output
