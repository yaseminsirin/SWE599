# DigitalOcean deployment guide — SWE599 Smart Jobs

## 1. Recommended deployment type

**Use a DigitalOcean Droplet with Docker Compose** (`docker-compose.prod.yml`).

| Requirement | Why Droplet wins |
|-------------|------------------|
| **pgvector + HNSW** | You control Postgres via `pgvector/pgvector:pg16`; migrations run `CREATE EXTENSION vector` and create HNSW indexes reliably. |
| **Redis + Celery worker + beat** | Three long-running processes plus web — matches existing Compose layout. |
| **sentence-transformers / PyTorch** | Image is ~1.5–2 GB; build pre-downloads MiniLM in Dockerfile. Droplet tolerates large images and long builds. |
| **Nightly ingest + embeddings** | Worker needs sustained CPU/RAM; Droplet gives predictable resources. |
| **Ollama (optional)** | Only possible on a Droplet if you install Ollama on the host — **not recommended for production**. Use Gemini or fallback instead. |

**App Platform** is possible but **not the safest choice** for this project:

- Managed Postgres supports pgvector, but extension + HNSW migration must be verified on your cluster tier.
- Worker + beat + web = 3 components; beat must be a **single instance**.
- Build may timeout or hit size limits with PyTorch + sentence-transformers.
- No practical way to run Ollama on App Platform.

**Recommendation:** Ubuntu 22.04/24.04 Droplet, **4 GB RAM / 2 vCPU minimum** (8 GB preferred for ingest + embeddings), Docker + Compose, optional Caddy/nginx for HTTPS.

---

## 2. Production environment variables (DigitalOcean)

Set these in the Droplet `.env` file (never commit `.env`). Grouped for App Platform “Environment Variables” UI if you use it later.

### Django

| Variable | Production value | Required |
|----------|------------------|----------|
| `DJANGO_SECRET_KEY` | Long random string (50+ chars) | **Yes** |
| `DJANGO_DEBUG` | `false` | **Yes** |
| `DJANGO_ALLOWED_HOSTS` | Your domain + droplet IP, e.g. `jobs.example.com,164.92.x.x` | **Yes** |
| `DJANGO_TIME_ZONE` | e.g. `UTC` or `Europe/Istanbul` | No |

### Database

| Variable | Production value | Required |
|----------|------------------|----------|
| `POSTGRES_DB` | e.g. `jobs_db` | **Yes** |
| `POSTGRES_USER` | e.g. `jobs_user` | **Yes** |
| `POSTGRES_PASSWORD` | Strong password | **Yes** |
| `POSTGRES_HOST` | `db` (Compose) or managed DB host | **Yes** |
| `POSTGRES_PORT` | `5432` | **Yes** |

**Managed Postgres on DO:** Use private connection string host/port. After first connect, ensure pgvector is enabled (migration `0002_pgvector_embedding` runs `VectorExtension()` — requires DB user permission to create extensions).

### Redis / Celery

| Variable | Production value | Required |
|----------|------------------|----------|
| `REDIS_URL` | `redis://redis:6379/0` (Compose) or managed Redis URL | **Yes** |
| `CELERY_BROKER_URL` | Same as `REDIS_URL` | **Yes** |
| `CELERY_RESULT_BACKEND` | Same as `REDIS_URL` | **Yes** |
| `INGEST_SCHEDULE_TIMEZONE` | e.g. `Europe/Istanbul` | No |
| `INGEST_SCHEDULE_HOUR` | e.g. `3` | No |
| `INGEST_SCHEDULE_MINUTE` | `0` | No |
| `ALERT_SCHEDULE_HOUR` | e.g. `4` (after ingest) | No |
| `ALERT_SCHEDULE_MINUTE` | `0` | No |

### Job source APIs (ingest)

| Variable | Required for nightly ingest |
|----------|----------------------------|
| `ADZUNA_APP_ID` | **Yes** |
| `ADZUNA_APP_KEY` | **Yes** |
| `ADZUNA_BASE_URL` | No (has default) |
| `ADZUNA_COUNTRY` | No |
| `USAJOBS_API_KEY` | **Yes** |
| `USAJOBS_USER_AGENT` | **Yes** (your email) |
| `USAJOBS_BASE_URL` | No |
| `REMOTIVE_BASE_URL` | No |
| `INGEST_PAGE_SIZE_*` / `INGEST_MAX_PAGES_*` | No |

### Email (Brevo REST API — production)

Alert emails use the Brevo Transactional Email API (HTTPS), not SMTP — works on DigitalOcean where outbound SMTP ports are blocked.

| Variable | Production value |
|----------|------------------|
| `BREVO_API_KEY` | Brevo API key (Brevo → SMTP & API → API keys) |
| `BREVO_API_TIMEOUT_SECONDS` | `30` (optional) |
| `DEFAULT_FROM_EMAIL` | Verified sender in Brevo (e.g. `yaseminsirin322@gmail.com`) |
| `SITE_URL` | Public URL, e.g. `http://104.248.113.186:8000` |

```env
BREVO_API_KEY=your-brevo-api-key
BREVO_API_TIMEOUT_SECONDS=30
DEFAULT_FROM_EMAIL=yaseminsirin322@gmail.com
SITE_URL=http://104.248.113.186:8000
```

### Semantic embeddings (production — do not change)

```env
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
EMBEDDING_STRICT_PROVIDER=true
EMBEDDING_BATCH_SIZE=50
EMBEDDING_MAX_JOBS_PER_RUN=500
EMBEDDING_TECH_ONLY=true
SEMANTIC_TECH_ONLY=true
SEMANTIC_REAL_SOURCES_ONLY=true
SEMANTIC_SEARCH_CANDIDATE_POOL=100
SEMANTIC_RERANK_WEIGHT_SEMANTIC=0.7
SEMANTIC_RERANK_WEIGHT_LEXICAL=0.3
```

Do **not** set `EMBEDDING_PROVIDER=gemini` in production.

### RAG / LLM (production)

**Option A — Gemini RAG (recommended on DO when you have a key):**

```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
GEMINI_API_KEY=<set in DO secrets / server .env only>
LLM_TIMEOUT_SECONDS=30
```

**Option B — Fallback only (no LLM key):**

```env
LLM_PROVIDER=
LLM_MODEL=
GEMINI_API_KEY=
```

Alert emails still send: plain intro + job list + tracking links. Processing never fails.

**Do not use Ollama on App Platform.** On a Droplet, only configure Ollama if you install it on the host and expose port 11434 — not required for production.

### Security / hosts

| Variable | Notes |
|----------|-------|
| `DJANGO_SECRET_KEY` | Secret — rotate if ever leaked |
| `DJANGO_DEBUG` | Must be `false` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated, no spaces |
| `SITE_URL` | Used in alert email tracking links |
| `POSTGRES_PASSWORD` | Secret |
| `GEMINI_API_KEY` | Secret — optional |
| `ADZUNA_APP_KEY`, `USAJOBS_API_KEY` | Secrets |

---

## 3. Secrets audit (as of repo check)

| Location | Status |
|----------|--------|
| `.env` | **Untracked** — contains a real `GEMINI_API_KEY`. **Do not commit.** Rotate the key if it was ever shared or pushed. |
| `.env.example` | Safe — empty placeholders only |
| `settings.py` | Safe — reads from env, dev defaults only |
| `docs/` | Safe — placeholder examples (`your-key`, `sk-...`) |
| Git history | No `AIza` keys found in committed files |

**Immediate cleanup steps:**

1. Add `.gitignore` (included in repo) — ensures `.env` is ignored.
2. Never `git add .env`.
3. If `.env` was ever committed: rotate all keys, `git filter-repo` or BFG to purge history, force-push only if you accept rewriting history.
4. Store production secrets only in DigitalOcean Droplet `.env` or App Platform encrypted env UI.

---

## 4. Docker / production readiness

| Item | Status |
|------|--------|
| **sentence-transformers in Dockerfile** | Yes — CPU torch via `requirements.txt`, model pre-downloaded at build |
| **First-run model** | Baked into image; no HuggingFace download needed at runtime if build succeeded |
| **collectstatic** | `docker-compose.prod.yml` runs `collectstatic` before gunicorn; `STATIC_ROOT` + WhiteNoise when `DJANGO_DEBUG=false` |
| **Migrations** | Auto on web/beat start; pgvector extension via migration `0002` |
| **HNSW index** | Created in `0002` and recreated in `0004` (384-dim) |
| **Celery worker** | `celery -A config worker` in prod compose |
| **Redis** | Required; broker + result backend |
| **Dev vs prod** | Dev: `docker-compose.yml` + runserver. Prod: `docker-compose.prod.yml` + gunicorn |

**Resource note:** First embedding batch after deploy is CPU-heavy; use at least 4 GB RAM.

---

## 5. DigitalOcean Droplet setup (recommended)

### 5.1 Create Droplet

1. DigitalOcean → **Create Droplet**
2. **Ubuntu 24.04**, **4 GB RAM / 2 vCPU** (8 GB if budget allows)
3. Add SSH key
4. Optional: assign domain A record to droplet IP

### 5.2 Server bootstrap

```bash
ssh root@YOUR_DROPLET_IP

apt update && apt upgrade -y
apt install -y docker.io docker-compose-plugin git
systemctl enable --now docker

# Deploy user (optional)
adduser deploy
usermod -aG docker deploy
```

### 5.3 Deploy application

```bash
su - deploy
git clone <your-repo-url> swe599
cd swe599
cp .env.example .env
nano .env   # set all production vars (section 2)
```

**Production `.env` highlights:**

```env
DJANGO_SECRET_KEY=<generate-strong-key>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=your-domain.com,YOUR_DROPLET_IP
SITE_URL=https://your-domain.com

LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
GEMINI_API_KEY=<your-key-or-leave-empty-for-fallback>

BREVO_API_KEY=<your-brevo-api-key>
DEFAULT_FROM_EMAIL=yaseminsirin322@gmail.com
```

### 5.4 Build and start

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

All services should be **Up**: `web`, `worker`, `beat`, `db`, `redis`.

### 5.5 HTTPS (Caddy example)

```bash
sudo apt install -y caddy
sudo nano /etc/caddy/Caddyfile
```

```caddy
your-domain.com {
    reverse_proxy localhost:8000
}
```

```bash
sudo systemctl reload caddy
```

Update `SITE_URL=https://your-domain.com` and restart web.

### 5.6 Alternative: Managed Postgres + Redis

Point `POSTGRES_HOST` / `REDIS_URL` at DO managed services. Keep `web`, `worker`, `beat` on the Droplet. Ensure:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

(run once if migration lacks permission)

---

## 5b. App Platform (not recommended — reference only)

If you still use App Platform:

| Component | Type | Command |
|-----------|------|---------|
| **web** | Web Service | Build: `pip install -r requirements.txt` (Dockerfile preferred) / Run: gunicorn (see prod compose) |
| **worker** | Worker | `celery -A config worker -l info` |
| **beat** | Worker (1 instance only) | `python manage.py setup_nightly_schedule && celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler` |
| **db** | Managed Postgres 16 + enable pgvector | |
| **redis** | Managed Redis | |

**Pre-deploy job (App Platform):** `python manage.py migrate --noinput && python manage.py collectstatic --noinput`

**Risk:** Docker build with PyTorch may exceed build time limits; pgvector/HNSW must be verified on managed DB.

---

## 6. Post-deploy commands

Run from project root on the Droplet:

```bash
COMPOSE="docker compose -f docker-compose.prod.yml"

# Migrations (also run on web/beat start)
$COMPOSE exec web python manage.py migrate --noinput

# Static files (also run on web start)
$COMPOSE exec web python manage.py collectstatic --noinput

# Admin user
$COMPOSE exec web python manage.py createsuperuser

# Register nightly ingest + alert schedules in DB
$COMPOSE exec beat python manage.py setup_nightly_schedule

# First data load (do not wait for 03:00)
$COMPOSE exec web python manage.py shell -c "
from apps.jobs.tasks import nightly_job_refresh_task
print(nightly_job_refresh_task())
"

# Audit embeddings
$COMPOSE exec web python manage.py audit_embeddings

# Regenerate tech embeddings (real jobs only)
$COMPOSE exec web python manage.py regenerate_embeddings --relevant-only --limit 2000

# Manual alert run
$COMPOSE exec web python manage.py process_alerts --min 10 --max 20

# Test Gemini/Ollama RAG without sending email
$COMPOSE exec web python manage.py test_ollama_rag --keyword "python developer" --max-jobs 3
# (requires LLM_PROVIDER=ollama — skip on production if using Gemini)

# Smoke tests
$COMPOSE exec web python manage.py test apps.search.tests.test_pgvector apps.alerts.tests -v2
```

---

## 7. Smoke test checklist

After deploy, verify:

| Check | How |
|-------|-----|
| `/search/` opens | Browser → `https://your-domain.com/search/` |
| Keyword search | Query `python`, mode Keyword |
| Semantic search | Query `python developer`, mode Semantic — score badges appear |
| pgvector query | Semantic returns results (requires embeddings) |
| Alert creation | Search → Create Alert → email + keyword → submit |
| `process_alerts` | `$COMPOSE exec web python manage.py process_alerts --min 10 --max 20` → `rag_emails` or `fallback_emails` > 0 |
| RAG / fallback email | Console/log shows explanation + Highlights (Gemini) or plain intro (fallback) |
| Tracking redirect | Open an alert email Apply link → `/api/tracking/alert-click/...` → redirects to job URL |
| Admin | `/admin/` after `createsuperuser` |

**Expected RAG summary with Gemini:**

```python
{'rag_emails': 1, 'fallback_emails': 0, 'errors': []}
```

**Expected with no LLM key:**

```python
{'rag_emails': 0, 'fallback_emails': 1, 'errors': []}
```

---

## 8. Quick reference

```bash
# Production lifecycle
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f web worker beat
docker compose -f docker-compose.prod.yml restart web worker beat

# Logs
docker compose -f docker-compose.prod.yml logs worker --tail 100
```

See also: [DEPLOYMENT_REQUIREMENTS.md](../DEPLOYMENT_REQUIREMENTS.md), [RAG_ALERTS.md](RAG_ALERTS.md).
