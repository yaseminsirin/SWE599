import html

from apps.jobs.models import JobPosting
from apps.jobs.services.job_labels import format_location_display

from ...models import JobAlert
from .email_generation import AlertEmailContent, build_alert_job_url
from .job_context import format_user_alert_preferences, get_alert_query_label


def _esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def _source_label(source: str) -> str:
    labels = {
        "adzuna": "Adzuna",
        "usajobs": "USAJOBS",
        "remotive": "Remotive",
    }
    return labels.get((source or "").lower(), (source or "Job board").title())


def _job_match_note(content: AlertEmailContent, index: int, job: JobPosting, query: str) -> str:
    if index < len(content.job_match_notes) and content.job_match_notes[index].strip():
        return content.job_match_notes[index].strip()
    title = job.title or "This role"
    return f"Related to your \"{query}\" alert through the title and listed responsibilities at {job.company_name or 'the company'}."


def compose_alert_email_html(
    content: AlertEmailContent,
    jobs: list[JobPosting],
    *,
    alert: JobAlert,
) -> str:
    query = get_alert_query_label(alert)
    job_count = len(jobs)
    prefs = format_user_alert_preferences(alert)

    signals_html = ""
    if content.key_signals:
        signal_items = "".join(
            f'<li style="margin:0 0 8px 0;color:#334155;">{_esc(item)}</li>'
            for item in content.key_signals
        )
        signals_html = f"""
        <div style="margin:24px 0 0 0;">
          <h2 style="margin:0 0 12px 0;font-size:16px;color:#0f172a;">Key Match Signals</h2>
          <ul style="margin:0;padding-left:20px;">{signal_items}</ul>
        </div>
        """

    pref_html = ""
    if prefs:
        pref_items = "".join(
            f'<span style="display:inline-block;margin:0 8px 8px 0;padding:6px 10px;background:#eef2ff;color:#4338ca;border-radius:999px;font-size:12px;">{_esc(item)}</span>'
            for item in prefs
        )
        pref_html = f'<div style="margin-top:14px;">{pref_items}</div>'

    job_cards = []
    for index, job in enumerate(jobs):
        location = format_location_display(
            location_text=job.location_text,
            city=job.city,
            country=job.country,
            is_remote=job.is_remote,
        )
        apply_url = build_alert_job_url(alert=alert, job=job)
        match_note = _job_match_note(content, index, job, query)
        job_cards.append(
            f"""
            <div style="border:1px solid #e2e8f0;border-radius:12px;padding:18px;margin-bottom:14px;background:#ffffff;">
              <div style="font-size:17px;font-weight:700;color:#0f172a;margin-bottom:6px;">{_esc(job.title or "Untitled")}</div>
              <div style="font-size:14px;color:#475569;margin-bottom:4px;"><strong>Company:</strong> {_esc(job.company_name or "Not specified")}</div>
              <div style="font-size:14px;color:#475569;margin-bottom:4px;"><strong>Location:</strong> {_esc(location or "Not specified")}</div>
              <div style="font-size:14px;color:#475569;margin-bottom:10px;"><strong>Source:</strong> {_esc(_source_label(job.source))}</div>
              <div style="font-size:13px;color:#64748b;margin-bottom:14px;line-height:1.5;"><em>Why it matches:</em> {_esc(match_note)}</div>
              <a href="{_esc(apply_url)}" style="display:inline-block;background:#4f46e5;color:#ffffff;text-decoration:none;padding:10px 16px;border-radius:8px;font-size:14px;font-weight:600;">View job</a>
            </div>
            """
        )

    jobs_html = "".join(job_cards)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JobSense AI Alert</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">AI-curated job matches based on your alert preferences.</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f1f5f9;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;">
          <tr>
            <td style="background:linear-gradient(135deg,#4f46e5 0%,#6366f1 100%);padding:28px 24px;color:#ffffff;">
              <div style="font-size:24px;font-weight:700;letter-spacing:-0.02em;">JobSense AI</div>
              <div style="font-size:14px;opacity:0.95;margin-top:6px;">Personalized job alert</div>
            </td>
          </tr>
          <tr>
            <td style="padding:24px;">
              <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:18px;">
                <div style="font-size:15px;line-height:1.6;color:#334155;">
                  We found <strong>{job_count}</strong> relevant job opportunit{"y" if job_count == 1 else "ies"} for your alert:
                  <span style="display:inline-block;margin-top:8px;padding:8px 12px;background:#eef2ff;color:#4338ca;border-radius:8px;font-weight:700;">{_esc(query)}</span>
                </div>
                {pref_html}
              </div>

              <div style="margin:24px 0 0 0;">
                <h2 style="margin:0 0 12px 0;font-size:16px;color:#0f172a;">Why these jobs match</h2>
                <div style="font-size:14px;line-height:1.7;color:#334155;">{_esc(content.summary)}</div>
              </div>

              {signals_html}

              <div style="margin:28px 0 0 0;">
                <h2 style="margin:0 0 14px 0;font-size:16px;color:#0f172a;">Matching Jobs</h2>
                {jobs_html}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 24px;background:#f8fafc;border-top:1px solid #e2e8f0;font-size:12px;line-height:1.6;color:#64748b;">
              You received this email because you created a JobSense AI alert.<br>
              JobSense AI — SWE599 Project
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def compose_alert_email_text(
    content: AlertEmailContent,
    jobs: list[JobPosting],
    *,
    alert: JobAlert,
) -> str:
    query = get_alert_query_label(alert)
    lines: list[str] = [
        "JobSense AI",
        "Personalized job alert",
        "",
        f"We found {len(jobs)} relevant job opportunit{'y' if len(jobs) == 1 else 'ies'} for your alert: {query}",
    ]

    prefs = format_user_alert_preferences(alert)
    if prefs:
        lines.append("")
        lines.append("Preferences: " + " · ".join(prefs))

    lines.extend(["", "Why these jobs match", content.summary, ""])

    if content.key_signals:
        lines.append("Key Match Signals")
        for item in content.key_signals:
            lines.append(f"• {item}")
        lines.append("")

    lines.append("Matching Jobs")
    for index, job in enumerate(jobs):
        location = format_location_display(
            location_text=job.location_text,
            city=job.city,
            country=job.country,
            is_remote=job.is_remote,
        )
        apply_url = build_alert_job_url(alert=alert, job=job)
        match_note = _job_match_note(content, index, job, query)
        lines.extend(
            [
                "",
                job.title or "Untitled",
                f"Company: {job.company_name or 'Not specified'}",
                f"Location: {location or 'Not specified'}",
                f"Source: {_source_label(job.source)}",
                f"Why it matches: {match_note}",
                f"View job: {apply_url}",
            ]
        )

    lines.extend(["", "You received this email because you created a JobSense AI alert.", "JobSense AI — SWE599 Project"])
    return "\n".join(lines).strip() + "\n"
