# Job Aggregation and Intelligent Search System

## 1) Project Overview

MVP backend for aggregating jobs from multiple APIs, normalizing records, and providing:
- keyword search
- semantic search (embedding-based)
- ranked search (keyword + semantic + click signal)
- user alerts with email notifications
- search/click tracking

Tech stack:
- Django + Django REST Framework
- PostgreSQL, Redis
- Celery + Celery Beat
- Docker Compose

---

## 2) Setup Instructions

1. Copy env template:
   - `cp .env.example .env`
2. Start services:
   - `docker compose up --build`
3. Run migrations:
   - `docker compose exec web python manage.py migrate`
4. (Optional) Create admin user:
   - `docker compose exec web python manage.py createsuperuser`

---

## 3) Environment Variables

Core:
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`
- `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`

Source APIs:
- `ADZUNA_BASE_URL`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `ADZUNA_COUNTRY`
- `USAJOBS_BASE_URL`, `USAJOBS_API_KEY`, `USAJOBS_USER_AGENT`
- `REMOTIVE_BASE_URL`

Ingestion / ranking / embeddings:
- `INGEST_PAGE_SIZE`, `INGEST_MAX_PAGES`, `INGEST_MAX_PAGES_ADZUNA`, `INGEST_MAX_PAGES_USAJOBS`, `INGEST_MAX_PAGES_REMOTIVE`
- `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL_NAME`, `EMBEDDING_DIMENSION`
- `RANKING_WEIGHT_KEYWORD`, `RANKING_WEIGHT_SEMANTIC`, `RANKING_WEIGHT_CLICK`

Email:
- `EMAIL_BACKEND`
- `DEFAULT_FROM_EMAIL`

---

## 4) Run Commands

With Docker:
- Start app stack: `docker compose up --build`
- Run migrations: `docker compose exec web python manage.py migrate`
- Django shell: `docker compose exec web python manage.py shell`

Celery:
- Worker runs in `worker` service
- Beat runs in `beat` service

Useful manual tasks (inside `web`):
- Ingest all sources:  
  `python manage.py shell -c "from apps.jobs.tasks import ingest_all_sources_task; print(ingest_all_sources_task())"`
- Normalize raw records:  
  `python manage.py shell -c "from apps.jobs.tasks import normalize_raw_records_task; print(normalize_raw_records_task())"`
- Generate missing embeddings:  
  `python manage.py shell -c "from apps.search.tasks import generate_missing_job_embeddings_task; print(generate_missing_job_embeddings_task())"`
- Process alerts:  
  `python manage.py shell -c "from apps.alerts.tasks import process_job_alerts_task; print(process_job_alerts_task())"`

---

## 5) Test Commands

Run focused MVP test suites:
- `python backend/manage.py test apps.jobs.tests apps.search.tests apps.alerts.tests apps.tracking.tests -v 2`

Or run all tests:
- `python backend/manage.py test -v 2`

---

## 6) Demo Flow (Presentation)

Recommended order:
1. **Ingestion + normalization**
   - run ingestion task
   - run normalization task
   - show created `JobPosting` records
2. **Search APIs**
   - `/api/jobs/search/` for keyword/filter
   - `/api/jobs/semantic-search/` for semantic relevance
   - `/api/jobs/ranked-search/` for combined ranking
3. **Auth + alerts**
   - register/login
   - create alert
   - run alert processing task
   - show console email output
4. **Tracking + ranking feedback**
   - send tracking click events
   - rerun ranked search and show score/rank fields

---

## 7) Key API Endpoints

Auth:
- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/logout/`

Jobs:
- `GET /api/jobs/`
- `GET /api/jobs/{id}/`
- `GET /api/jobs/search/`
- `GET /api/jobs/semantic-search/`
- `GET /api/jobs/ranked-search/`

Alerts:
- `POST /api/alerts/`
- `GET /api/alerts/`
- `GET /api/alerts/{id}/`
- `PATCH /api/alerts/{id}/`
- `DELETE /api/alerts/{id}/`

Tracking:
- `POST /api/tracking/search/`
- `POST /api/tracking/click/`
