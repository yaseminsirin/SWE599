from typing import Any

from apps.jobs.services.job_labels import infer_is_remote, normalize_employment_slug

from .base import BaseRawNormalizer, build_content_hash, clean_text, parse_datetime, parse_decimal


class AdzunaNormalizer(BaseRawNormalizer):
    source_name = "adzuna"

    def normalize(self, payload: dict[str, Any], *, source_job_id: str) -> dict[str, Any]:
        location_data = payload.get("location", {}) or {}
        area = location_data.get("area", []) if isinstance(location_data, dict) else []
        location_text = clean_text(location_data.get("display_name") or " ".join(area[-2:]))

        title = clean_text(payload.get("title"))
        company_name = clean_text((payload.get("company") or {}).get("display_name"))
        description_raw = clean_text(payload.get("description"))
        normalized_title = title.lower()
        description_clean = description_raw

        contract_raw = payload.get("contract_type") or payload.get("contract_time") or ""
        employment_slug = normalize_employment_slug(contract_raw)
        category_label = clean_text((payload.get("category") or {}).get("label"))
        is_remote = infer_is_remote(
            is_remote=False,
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
                "job_url": payload.get("redirect_url") or payload.get("url") or "",
                "location_text": location_text,
                "city": clean_text(area[-2] if len(area) >= 2 else ""),
                "country": clean_text(area[-1] if area else ""),
                "is_remote": is_remote,
                "employment_type": employment_slug,
                "posted_at": parse_datetime(payload.get("created")),
                "expires_at": None,
                "salary_min": parse_decimal(payload.get("salary_min")),
                "salary_max": parse_decimal(payload.get("salary_max")),
                "salary_currency": clean_text(payload.get("salary_currency")) or "USD",
                "salary_period": "",
                "category_raw": category_label,
                "category_normalized": category_label.lower(),
            }
        )
        output["content_hash"] = build_content_hash(
            normalized_title=normalized_title,
            company_name=company_name,
            location_text=location_text,
            description_clean=description_clean,
        )
        return output
