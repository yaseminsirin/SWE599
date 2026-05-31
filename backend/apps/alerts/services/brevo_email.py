import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_transactional_email(
    *,
    recipient: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> dict:
    """
    Send email via Brevo Transactional Email API (HTML + plain-text).

    Raises on configuration or API errors. Caller should catch per-alert.
    """
    api_key = getattr(settings, "BREVO_API_KEY", "").strip()
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "").strip()
    from_name = getattr(settings, "DEFAULT_FROM_NAME", "").strip()

    if not api_key:
        raise ValueError("BREVO_API_KEY is not configured")
    if not from_email:
        raise ValueError("DEFAULT_FROM_EMAIL is not configured")
    if not (recipient or "").strip():
        raise ValueError("recipient email is required")

    sender: dict[str, str] = {"email": from_email}
    if from_name:
        sender["name"] = from_name

    payload = {
        "sender": sender,
        "to": [{"email": recipient.strip()}],
        "subject": subject,
        "textContent": body,
    }
    if html_body:
        payload["htmlContent"] = html_body
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }

    try:
        response = requests.post(
            BREVO_API_URL,
            json=payload,
            headers=headers,
            timeout=getattr(settings, "BREVO_API_TIMEOUT_SECONDS", 30),
        )
        response.raise_for_status()
        data = response.json() if response.content else {}
        logger.debug("Brevo email sent to %s: %s", recipient, data)
        return data
    except requests.RequestException as exc:
        detail = ""
        if exc.response is not None:
            detail = (exc.response.text or "")[:500]
        logger.exception(
            "Brevo email failed for %s (subject=%r): %s %s",
            recipient,
            subject,
            exc,
            detail,
        )
        raise
