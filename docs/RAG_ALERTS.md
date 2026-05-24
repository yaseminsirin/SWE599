# RAG job alert emails

Retrieval is **not** done by the LLM. Nightly alerts select jobs via the existing search pipeline (keyword filters + local sentence-transformers embeddings + pgvector + hybrid reranking). RAG only writes the email introduction and highlights from that retrieved list.

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

## Test RAG only (no email sent)

```bash
docker compose exec web python manage.py test_ollama_rag --keyword "python developer" --max-jobs 5
```

This prints:

- Retrieved jobs
- System prompt and user prompt
- Raw Ollama output
- Parsed `EXPLANATION` and `HIGHLIGHTS`
- `FALLBACK TRIGGERED? yes/no`
- Composed email preview (not sent)

Requires `LLM_PROVIDER=ollama` in `.env`.

## Process alerts with Ollama

```bash
docker compose exec web python manage.py process_alerts --min 10 --max 20
```

Success indicators:

- Summary shows `rag_emails` > 0 and `fallback_emails` = 0
- Console email body includes narrative text plus a **Highlights:** section
- Each job has an **Apply:** link via `/api/tracking/alert-click/<job_id>/?alert_id=<id>`

## If Ollama is not reachable

The system **does not fail**. `generate_alert_email_content()` catches errors and returns fallback copy:

- Plain explanation: “We found N software/tech job(s)…”
- Full job list with tracking URLs
- `used_rag=False`, `rag_emails=0`, `fallback_emails` incremented

Typical errors:

- `ConnectionError` / `Network is unreachable` — Ollama not running or wrong `OLLAMA_BASE_URL`
- `404 model 'llama3.2' not found` — run `ollama pull llama3.2` on the host
- `Read timed out` — increase `LLM_TIMEOUT_SECONDS` (e.g. 120)

Check worker logs for `RAG email generation failed for alert …` warnings.

## Sample RAG email (Ollama)

```
These roles align with your python developer alert across software and security engineering positions.

Highlights:
- Senior software engineer roles at Lockheed Martin (Maryland).
- Computer engineer (cybersecurity) at Bureau of Industry and Security (DC).
- Head of Engineering at Lemon.io (remote-friendly).

Matching jobs:
- Python Developer | Social Security Administration | Woodlawn, Maryland
  Apply: http://localhost:8000/api/tracking/alert-click/1681/?alert_id=3
...
— JobSense AI
```

## Implementation notes

- Provider: `backend/apps/alerts/services/rag/llm/ollama_provider.py` — `POST {OLLAMA_BASE_URL}/api/chat`
- Factory: `LLM_PROVIDER=ollama` → `OllamaLLMProvider`
- Output format: `EXPLANATION:` + `HIGHLIGHTS:` (parsed in `job_context.py`)
- Nightly schedule: `python manage.py setup_nightly_schedule` registers `nightly-job-alerts`
