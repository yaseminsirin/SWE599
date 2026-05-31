import html
import json

from django.http import HttpResponse


def render_job_redirect_page(*, target_url: str | None, search_url: str) -> HttpResponse:
    """HTML interstitial for email clients that mishandle 302 redirects."""
    safe_search = html.escape(search_url, quote=True)

    if not target_url:
        body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Job listing unavailable</title>
</head>
<body style="margin:0;font-family:Arial,sans-serif;background:#ffffff;color:#0f172a;">
  <div style="max-width:480px;margin:48px auto;padding:24px;text-align:center;">
    <p style="font-size:18px;margin-bottom:16px;">This job listing link is no longer available.</p>
    <p><a href="{safe_search}" style="color:#4f46e5;font-weight:600;">Search for jobs on JobSense AI</a></p>
  </div>
</body>
</html>"""
        return HttpResponse(body, content_type="text/html; charset=utf-8")

    safe_target = html.escape(target_url, quote=True)
    js_target = json.dumps(target_url)

    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="0;url={safe_target}">
  <title>Opening job listing</title>
</head>
<body style="margin:0;font-family:Arial,sans-serif;background:#ffffff;color:#0f172a;">
  <div style="max-width:480px;margin:48px auto;padding:24px;text-align:center;">
    <p style="font-size:18px;margin-bottom:16px;">Opening job listing…</p>
    <p><a href="{safe_target}" style="color:#4f46e5;font-weight:600;">Tap here if the page does not open</a></p>
  </div>
  <script>window.location.replace({js_target});</script>
</body>
</html>"""
    return HttpResponse(body, content_type="text/html; charset=utf-8")
