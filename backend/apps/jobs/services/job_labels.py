import ast
import re
from typing import Any


def clean_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text

EMPLOYMENT_LABELS = {
    "full_time": "Full time",
    "part_time": "Part time",
    "contract": "Contract",
    "permanent": "Permanent",
    "temporary": "Temporary",
    "internship": "Internship",
}

USAJOBS_SCHEDULE_CODE_LABELS = {
    "1": "Full time",
    "2": "Part time",
    "3": "Full time",
    "4": "Seasonal",
    "5": "Intermittent",
    "6": "Full time",
}


def extract_structured_text(value: Any) -> str:
    """Pull human text from USAJOBS-style lists/dicts or plain strings."""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and ("Code" in text or "Name" in text):
            try:
                value = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                return ""
        else:
            return clean_text(text)
    if isinstance(value, dict):
        return clean_text(
            value.get("Name")
            or value.get("name")
            or value.get("Label")
            or value.get("label")
            or ""
        )
    if isinstance(value, (list, tuple)):
        parts = [extract_structured_text(item) for item in value]
        return clean_text(", ".join(p for p in parts if p))
    return clean_text(value)


def _slug_from_usajobs_codes(value: Any) -> str:
    items = value
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            items = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return ""
    if not isinstance(items, (list, tuple)):
        return ""
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("Code") or "").strip()
        label = USAJOBS_SCHEDULE_CODE_LABELS.get(code, "")
        if label:
            return normalize_employment_slug(label)
    return ""


def normalize_employment_slug(value: Any) -> str:
    text = extract_structured_text(value).lower()
    if not text:
        return _slug_from_usajobs_codes(value)
    if text in {"-", "—", "n/a", "na", "none", "unknown", "[]"}:
        return ""

    normalized = text.replace("-", " ").replace("_", " ")

    if "full" in normalized and "time" in normalized:
        return "full_time"
    if "part" in normalized and "time" in normalized:
        return "part_time"
    if "contract" in normalized or "contractor" in normalized:
        return "contract"
    if "permanent" in normalized:
        return "permanent"
    if "temporary" in normalized or "temp" in normalized.split():
        return "temporary"
    if "intern" in normalized:
        return "internship"

    slug_candidate = normalized.replace(" ", "_")
    if slug_candidate in EMPLOYMENT_LABELS:
        return slug_candidate
    return ""


def employment_type_label(slug: str) -> str:
    if not slug:
        return ""
    return EMPLOYMENT_LABELS.get(slug, "")


def employment_label_from_raw(value: Any) -> str:
    """Best display label for API/UI (may differ from stored slug)."""
    slug = normalize_employment_slug(value)
    if slug:
        return employment_type_label(slug)

    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, dict):
                code = str(item.get("Code") or "").strip()
                name = clean_text(item.get("Name") or "")
                if name:
                    slug = normalize_employment_slug(name)
                    if slug:
                        return employment_type_label(slug)
                    return name[:40]
                if code in USAJOBS_SCHEDULE_CODE_LABELS:
                    return USAJOBS_SCHEDULE_CODE_LABELS[code]
    return ""


def infer_is_remote(
    *,
    is_remote: bool | None,
    source: str = "",
    title: str = "",
    description: str = "",
    location: str = "",
    employment_slug: str = "",
) -> bool:
    if is_remote is True:
        return True
    if source == "remotive":
        return True
    blob = f"{title} {description} {location} {employment_slug}".lower()
    remote_markers = (
        "remote",
        "work from home",
        "wfh",
        "telework",
        "tele-work",
        "hybrid remote",
        "virtual",
    )
    return any(marker in blob for marker in remote_markers)


def source_label(source: str) -> str:
    return {
        "adzuna": "Adzuna",
        "usajobs": "USAJOBS",
        "remotive": "Remotive",
    }.get(source or "", "")


USAJOBS_RATE_INTERVAL = {
    "PA": "year",
    "PH": "hour",
    "PM": "month",
    "WK": "week",
    "BI": "biweekly",
    "HO": "hour",
    "DA": "day",
}

PERIOD_SUFFIX = {
    "year": "/yr",
    "month": "/mo",
    "week": "/wk",
    "hour": "/hr",
    "day": "/day",
    "biweekly": "/2wk",
}


def _normalize_salary_parts(
    *,
    salary_min,
    salary_max,
    salary_currency: str,
    salary_period: str,
    source: str = "",
) -> tuple[float | None, float | None, str, str]:
    min_v = float(salary_min) if salary_min is not None else None
    max_v = float(salary_max) if salary_max is not None else None
    if min_v == 0:
        min_v = None

    currency = clean_text(salary_currency).upper()
    period = clean_text(salary_period).lower()

    if currency in USAJOBS_RATE_INTERVAL:
        if not period or period in {"pa", "ph", "pm", "wk", "bi", "ho", "da"}:
            period = USAJOBS_RATE_INTERVAL[currency]
        currency = "USD"

    if period in USAJOBS_RATE_INTERVAL:
        period = USAJOBS_RATE_INTERVAL[period.upper()]

    if period in {"0", "1", "true", "false"}:
        period = ""

    if not currency and source in {"adzuna", "usajobs"}:
        currency = "USD"

    return min_v, max_v, currency, period


def format_salary_display(
    *,
    salary_min,
    salary_max,
    salary_currency: str = "",
    salary_period: str = "",
    source: str = "",
) -> str:
    min_v, max_v, currency, period = _normalize_salary_parts(
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        salary_period=salary_period,
        source=source,
    )
    if min_v is None and max_v is None:
        return ""

    symbol = {"USD": "$", "GBP": "£", "EUR": "€", "CAD": "C$", "AUD": "A$"}.get(currency, "")
    prefix = symbol or (currency + " " if currency else "")

    def fmt(amount: float) -> str:
        if amount >= 1000:
            return f"{prefix}{amount:,.0f}"
        return f"{prefix}{amount:,.2f}".rstrip("0").rstrip(".")

    suffix = PERIOD_SUFFIX.get(period, f" / {period}" if period else "")

    if min_v is not None and max_v is not None and abs(min_v - max_v) > 1:
        return f"{fmt(min_v)} – {fmt(max_v)}{suffix}"
    if max_v is not None:
        return f"{fmt(max_v)}{suffix}"
    if min_v is not None:
        return f"{fmt(min_v)}{suffix}"
    return ""


def format_location_display(
    *,
    location_text: str = "",
    city: str = "",
    country: str = "",
    is_remote: bool = False,
) -> str:
    loc = clean_text(location_text)
    if loc:
        return loc
    parts = [clean_text(city), clean_text(country)]
    parts = [p for p in parts if p]
    if parts:
        return ", ".join(parts)
    if is_remote:
        return "Remote"
    return ""


def remote_label(*, is_remote: bool) -> str:
    return "Remote" if is_remote else "On-site"


def category_label_from_raw(value: Any) -> str:
    """USAJOBS JobCategory is often a list of {Code, Name} objects."""
    if value is None:
        return ""

    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and ("Code" in text or "Name" in text or "code" in text):
            try:
                value = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                return _truncate_category_label(text)
        elif not text.startswith("[{"):
            cleaned = clean_text(text)
            if cleaned and not cleaned.startswith("["):
                return _truncate_category_label(cleaned)
            return ""

    if isinstance(value, dict):
        name = clean_text(value.get("Name") or value.get("name") or "")
        if name:
            return _truncate_category_label(name)
        code = str(value.get("Code") or value.get("code") or "").strip()
        return _truncate_category_label(f"Occupation {code}") if code else ""

    if isinstance(value, (list, tuple)):
        names: list[str] = []
        for item in value:
            label = category_label_from_raw(item)
            if label and label not in names:
                names.append(label)
        if names:
            return _truncate_category_label(", ".join(names))

    return ""


def _truncate_category_label(text: str, max_len: int = 48) -> str:
    cleaned = clean_text(text)
    if not cleaned or cleaned.startswith("[{") or "'Code'" in cleaned:
        return ""
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1] + "…"
    return cleaned


def format_category_display(category: Any) -> str:
    return category_label_from_raw(category)
