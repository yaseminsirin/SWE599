# Final presentation — real API job data workflow

Use **Adzuna, USAJOBS, and Remotive** ingested jobs only. Do **not** use `seed_demo_jobs` for the final demo (optional for local UI testing only).

## Semantic search embeddings (local)

Semantic search uses **sentence-transformers** (`all-MiniLM-L6-v2`), **not** an LLM:

- Converts job text and queries into **384-dimensional** vectors
- Vectors are stored in **PostgreSQL pgvector** with an **HNSW** index
- **No embedding API quota** is required — runs fully inside Docker
- **RAG alert email generation** remains separate (optional Gemini/OpenAI LLM) and is unchanged

Gemini embeddings are **optional only** (`EMBEDDING_PROVIDER=gemini`) and are not used for the default demo stack.

## Why we do not embed all ~10k jobs at once

- After ingest you may have **10,000+** real `JobPosting` rows (mostly USAJOBS).
- For semantic search with `SEMANTIC_TECH_ONLY=true`, only **~1,500–1,700 tech-related** jobs matter for the demo.
- Local MiniLM can embed the full tech corpus in minutes; non-tech USAJOBS rows can be skipped.

## 1. Ingest and normalize

```bash
docker compose up -d
docker compose exec web python manage.py migrate

docker compose exec web python manage.py shell -c "
from apps.jobs.tasks import nightly_job_refresh_task
print(nightly_job_refresh_task())
"
```

## 2. Analyze source quality

```bash
docker compose exec web python manage.py analyze_job_sources
docker compose exec web python manage.py audit_embeddings
```

## 3. Environment (local sentence-transformers)

```env
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
EMBEDDING_STRICT_PROVIDER=true

EMBEDDING_BATCH_SIZE=50
EMBEDDING_MAX_JOBS_PER_RUN=500
EMBEDDING_SLEEP_SECONDS=0
EMBEDDING_TECH_ONLY=true

SEMANTIC_TECH_ONLY=true
SEMANTIC_SEARCH_CANDIDATE_POOL=100
SEMANTIC_RERANK_WEIGHT_SEMANTIC=0.7
SEMANTIC_RERANK_WEIGHT_LEXICAL=0.3
```

Rebuild after changing `.env` or embedding code:

```bash
docker compose build web worker
docker compose up -d --force-recreate web worker
```

## 4. pgvector dimension migration (768 → 384)

Migration `0004_embedding_384_minilm` clears old Gemini vectors and recreates the HNSW index at **384** dimensions.

```bash
docker compose exec web python manage.py migrate
```

Then regenerate embeddings (required after migration):

```bash
docker compose exec web python manage.py regenerate_embeddings --relevant-only
```

## 5. Embedding workflow (priority order)

Default priority when `--source` is omitted: **remotive → adzuna → usajobs**.

```bash
# Check progress
docker compose exec web python manage.py audit_embeddings

# Demo-relevant tech jobs (recommended)
docker compose exec web python manage.py regenerate_embeddings --relevant-only

# Or per source
docker compose exec web python manage.py regenerate_embeddings --source remotive --relevant-only --limit 100
docker compose exec web python manage.py regenerate_embeddings --source adzuna --relevant-only --limit 500
docker compose exec web python manage.py regenerate_embeddings --source usajobs --relevant-only --limit 500

# Non-tech jobs only if needed later
docker compose exec web python manage.py regenerate_embeddings --all-jobs --source usajobs --limit 100
```

`--relevant-only` is an alias for `--tech-only` (jobs matching `SEMANTIC_TECH_ONLY` heuristics).

## 6. Semantic search (pgvector + hybrid rerank)

- **pgvector** retrieves candidates by cosine distance on MiniLM vectors
- **Hybrid rerank** blends semantic + lexical scores
- Demo source `demo` is excluded automatically

```http
GET /api/jobs/semantic-search/?q=python+developer&tech_only=true
```

Response includes `semantic_score`, `lexical_score`, `hybrid_score`.

## 7. Safe live demo queries

- `python developer`
- `react developer`
- `backend developer`
- `frontend engineer`
- `data analyst`
- `business analyst`
- `devops engineer`

## 8. Verification checklist

```bash
docker compose exec web python manage.py audit_embeddings
docker compose exec web python manage.py test apps.search.tests.test_sentence_transformer_embeddings -v2
```

Confirm:

- Active provider is `sentence_transformers/all-MiniLM-L6-v2`
- Vector dimension **384**
- No active Gemini or hash-fallback rows
- Tech jobs embedded for semantic search

## 9. Clear demo seed data (if ever used)

```bash
docker compose exec web python manage.py seed_demo_jobs --clear-demo
```

See also: [DEPLOYMENT_REQUIREMENTS.md](../DEPLOYMENT_REQUIREMENTS.md), [PGVECTOR.md](PGVECTOR.md), [RAG_ALERTS.md](RAG_ALERTS.md).
