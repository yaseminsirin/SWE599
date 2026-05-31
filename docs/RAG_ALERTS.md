# RAG job alert emails

Retrieval is **not** done by the LLM. Nightly alerts select jobs via the existing search pipeline (keyword filters + local sentence-transformers embeddings + pgvector + hybrid reranking). RAG only writes the email copy (summary, key signals, per-job match notes) from that retrieved list.

Alert emails are sent as **professional HTML** via the **Brevo REST API** (`htmlContent` + `textContent` fallback). Internal fields such as `search_mode` or raw filter JSON are never shown to users.

Manual processing:

```bash
docker compose exec web python manage.py process_alerts --min 10 --max 20
```

Job links in alert emails go through `/api/tracking/alert-click/<job_id>/?alert_id=<alert_id>` before redirecting to the source listing URL.

## Final demo recommendation (local, no API quota)

Use **Ollama** on the host with **llama3.2** — reliable for presentations when Gemini/OpenAI quotas are unavailable.

```env
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2
OLLAMA_BASE_URL=http://host.docker.internal:11434
LLM_TIMEOUT_SECONDS=120
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
SITE_URL=http://localhost:8000
```

**Best alert keyword:** `python developer` (typically returns 10–20 real tech jobs).

After changing `.env`, recreate containers so env vars reload:

```bash
docker compose up -d --force-recreate web worker
```

## Environment variables

| Variable | Description |
|----------|-------------|
| `LLM_PROVIDER` | `openai`, `gemini`, `ollama`, or empty (fallback only) |
| `LLM_MODEL` | Model id (defaults: `gpt-4o-mini`, `gemini-2.0-flash`, `llama3.2`) |
| `LLM_TIMEOUT_SECONDS` | HTTP timeout (default `30`; use `120` for Ollama) |
| `OPENAI_API_KEY` | Required when `LLM_PROVIDER=openai` |
| `GEMINI_API_KEY` | Required when `LLM_PROVIDER=gemini` |
| `OLLAMA_BASE_URL` | Ollama HTTP API base (see Docker note below) |
| `SITE_URL` | Base URL for alert-click tracking links in emails |
| `BREVO_API_KEY` | Brevo transactional email API key (production) |
| `DEFAULT_FROM_EMAIL` | Verified sender address in Brevo |

Copy from `.env.example` and set secrets in `.env` (never commit keys).

## Provider setup

### Ollama (local — recommended for demo)

On the **host machine** (not inside Docker):

```bash
ollama serve          # if not already running
ollama pull llama3.2
```

Exact `.env` for Docker Desktop (Mac/Windows):

```env
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2
OLLAMA_BASE_URL=http://host.docker.internal:11434
LLM_TIMEOUT_SECONDS=120
```

Linux Docker: use host gateway IP or add `extra_hosts: ["host.docker.internal:host-gateway"]` to `docker-compose.yml` if `host.docker.internal` is unavailable.

### Gemini (cloud)

```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
GEMINI_API_KEY=your-key
```

If Gemini returns **429 quota exceeded**, alert processing still completes using the **plain fallback** email (jobs + tracking links). Switch to Ollama for a live RAG demo.

### OpenAI (cloud)

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

## Verify Ollama from Docker

Quick connectivity check (no RAG, no email):

```bash
docker compose exec web python -c "
import os, requests
url = os.getenv('OLLAMA_BASE_URL', 'http://host.docker.internal:11434').rstrip('/')
r = requests.get(url + '/api/tags', timeout=10)
print('status', r.status_code)
print(r.text[:500])
"
```

Expected: `status 200` and a JSON list including `llama3.2`.

## Preview email (no send)

```bash
docker compose exec web python manage.py preview_alert_email --keyword "backend developer" --max-jobs 5
# or
docker compose exec web python manage.py preview_alert_email --alert-id 3
```

Prints subject, plain text, and HTML preview. Uses RAG when configured, otherwise fallback copy.

## Test RAG only (no email sent)

```bash
docker compose exec web python manage.py test_ollama_rag --keyword "python developer" --max-jobs 5
```

This prints:

- Retrieved jobs
- System prompt and user prompt
- Raw Ollama output
- Parsed `SUMMARY`, `KEY_SIGNALS`, and `JOB_NOTES`
- `FALLBACK TRIGGERED? yes/no`
- Composed plain-text and HTML preview (not sent)

Requires `LLM_PROVIDER=ollama` in `.env`.

## Process alerts with Ollama

```bash
docker compose exec web python manage.py process_alerts --min 10 --max 20
```

Success indicators:

- Summary shows `rag_emails` > 0 and `fallback_emails` = 0 (when LLM is healthy)
- Brevo Activity Logs show delivered messages with HTML content
- Email subject: `JobSense AI Alert: <query> — <N> relevant matches`
- Each job card has a **View job** button linking via `/api/tracking/alert-click/<job_id>/?alert_id=<id>`

### Brevo Activity Logs

1. Log in to [Brevo](https://app.brevo.com) → **Transactional** → **Email** → **Logs** (or **Real time**).
2. Filter by recipient and time range after running `process_alerts`.
3. Open a message: confirm **Subject**, **HTML** preview (JobSense AI header, intro card, “Why these jobs match”, job cards), and delivery status **Delivered**.

## If Ollama is not reachable

The system **does not fail**. `generate_alert_email_content()` catches errors and returns fallback copy:

- Query-aware summary without internal filter fields
- Key Match Signals derived from job title/description tokens
- Full job list with tracking URLs (HTML + plain text)
- `used_rag=False`, `rag_emails=0`, `fallback_emails` incremented

Typical errors:

- `ConnectionError` / `Network is unreachable` — Ollama not running or wrong `OLLAMA_BASE_URL`
- `404 model 'llama3.2' not found` — run `ollama pull llama3.2` on the host
- `Read timed out` — increase `LLM_TIMEOUT_SECONDS` (e.g. 120)

Check worker logs for `RAG email generation failed for alert …` warnings.

## Implementation notes

- HTML composer: `backend/apps/alerts/services/rag/email_html.py`
- RAG copy: `backend/apps/alerts/services/rag/email_generation.py`
- LLM output format: `SUMMARY:` + `KEY_SIGNALS:` + `JOB_NOTES:` (parsed in `job_context.py`)
- Brevo sender: `backend/apps/alerts/services/brevo_email.py`
- Provider: `backend/apps/alerts/services/rag/llm/ollama_provider.py` — `POST {OLLAMA_BASE_URL}/api/chat`
- Factory: `LLM_PROVIDER=ollama` → `OllamaLLMProvider`
- Nightly schedule: `python manage.py setup_nightly_schedule` registers `nightly-job-alerts`
