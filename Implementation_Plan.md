# Implementation Plan

## Project Title
Job Aggregation and Intelligent Search System

## 1. Purpose

The purpose of this project is to develop a job aggregation platform that collects job postings from multiple external sources, normalizes them into a unified schema, and provides keyword search, semantic search, personalized ranking, and email-based job alerts.

The system will help users access job postings from different platforms in a single interface instead of searching each source separately. In addition, the project will include AI-supported semantic retrieval and user-behavior-based ranking improvements.

---

## 2. Implementation Approach

The system will be implemented as a Dockerized Django-based web application.

### Planned Technology Stack
- **Backend:** Django + Django REST Framework
- **Database:** PostgreSQL
- **Background Jobs / Scheduling:** Celery + Celery Beat
- **Message Broker:** Redis
- **Frontend:** Simple Django templates or a lightweight frontend layer
- **Containerization:** Docker + Docker Compose
- **Email Service:** SMTP or development email backend
- **Semantic Search / Embeddings:** pluggable embedding provider
- **Similarity Calculation:** cosine similarity
- **Version Control:** GitHub

The implementation will follow a modular architecture so that data ingestion, normalization, search, ranking, and alert processing are separated into manageable components.

---

## 3. High-Level System Architecture

The system will consist of the following main modules:

1. **Source Adapters**
   - Fetch job postings from external APIs
   - Initial sources:
     - Adzuna
     - USAJOBS
     - Remotive

2. **Normalization Layer**
   - Map heterogeneous source records into a unified internal schema
   - Standardize title, location, employment type, salary, and description fields
   - Generate duplicate detection hashes

3. **Persistence Layer**
   - Store raw source payloads
   - Store normalized job postings
   - Store user alerts and interaction logs

4. **Search Layer**
   - Keyword-based filtering and search
   - Semantic search with embeddings and cosine similarity

5. **Ranking Layer**
   - Combine keyword relevance, semantic similarity, and behavioral signals
   - Support configurable ranking weights

6. **Alert Layer**
   - Match newly ingested jobs with saved user alerts
   - Send top matching jobs by email

7. **Tracking Layer**
   - Record search queries
   - Record clicked jobs and clicked ranking positions

---

## 4. Development Phases

### Phase 1 - Project Setup
Goal: establish the project infrastructure.

Tasks:
- Create GitHub repository structure
- Create Dockerized Django project
- Configure PostgreSQL
- Configure Redis
- Configure Celery and Celery Beat
- Prepare environment variables
- Create initial app structure

Deliverable:
- Running local development environment with Docker Compose

---

### Phase 2 - Core Data Model Design
Goal: define database models for ingestion, normalized jobs, alerts, and tracking.

Planned core models:
- `RawJobRecord`
- `JobPosting`
- `JobEmbedding`
- `JobAlert`
- `UserSearchEvent`
- `JobClickEvent`

#### Example unified job fields
- source
- source_job_id
- title
- normalized_title
- company_name
- description_raw
- description_clean
- job_url
- location_text
- city
- country
- is_remote
- employment_type
- posted_at
- expires_at
- salary_min
- salary_max
- salary_currency
- salary_period
- category_raw
- category_normalized
- content_hash
- fetched_at
- normalized_at

Deliverable:
- Initial schema and migrations

---

### Phase 3 - Multi-Source Job Ingestion
Goal: fetch jobs from three external APIs.

Tasks:
- Implement Adzuna adapter
- Implement USAJOBS adapter
- Implement Remotive adapter
- Store raw job responses
- Handle pagination if necessary
- Add error logging and retry behavior

Implementation note:
Each source will be implemented using an adapter pattern so that new sources can be added later without redesigning the system.

Deliverable:
- Background job that successfully fetches jobs from all selected sources

---

### Phase 4 - Normalization and Deduplication
Goal: transform raw records into unified job postings.

Tasks:
- Map source-specific fields into the internal schema
- Normalize:
  - title
  - employment type
  - location
  - salary
  - description
- Generate content hash
- Detect duplicate or near-duplicate records
- Insert or update normalized jobs

Deduplication strategy:
- Exact and near-exact comparison using:
  - source-independent content hash
  - normalized title
  - company name
  - location
- Later extension:
  - semantic similarity for near-duplicate jobs

Deliverable:
- End-to-end ingestion + normalization pipeline

---

### Phase 5 - Search API and Basic Search Interface
Goal: provide searchable access to normalized jobs.

Tasks:
- Create REST API endpoints for:
  - job listing
  - job detail
  - filtered search
- Support filtering by:
  - keyword
  - location
  - remote
  - employment type
- Add pagination
- Create simple UI or browsable API for testing

Deliverable:
- Usable keyword-based job search

---

### Phase 6 - Semantic Search
Goal: improve job retrieval with embeddings.

Tasks:
- Select an embedding provider
- Generate embeddings for normalized job descriptions
- Generate embeddings for user queries
- Compute cosine similarity
- Combine semantic similarity with keyword relevance
- Return ranked results

Implementation note:
The system should not be tied permanently to a single embedding provider. Embedding generation will be abstracted behind a service layer.

Deliverable:
- Working semantic search prototype

---

### Phase 7 - User Management and Alerts
Goal: allow users to save searches and receive job alerts.

Tasks:
- Implement basic user registration and login
- Implement alert creation API
- Store query + filters as alert definitions
- Compare newly ingested jobs against user alerts
- Send email notifications with top matching jobs

Implementation choice for MVP:
- Keep authentication-based alert ownership as the default flow because it provides clear user ownership, secure alert management, and clean update/delete behavior.
- Future enhancement: add an optional lightweight email-only alert signup flow where the system can create a lightweight account or map alerts to an email identity behind the scenes.
- This future flow should not replace the authenticated flow; it should be an additional onboarding option.

Alert behavior:
- Triggered after scheduled ingestion
- Only new matching jobs should be included
- Maximum 20 results per email

Deliverable:
- Working alert creation and notification flow

---

### Phase 8 - Interaction Tracking and Personalized Ranking
Goal: improve search results using user behavior.

Tasks:
- Store search events
- Store job click events
- Record result position for clicked jobs
- Design weighted ranking formula
- Boost jobs similar to previously clicked jobs
- Support future RAG-based ranking improvements

Possible ranking inputs:
- keyword match score
- semantic similarity score
- click-based preference score
- recency score

Deliverable:
- Personalized ranking prototype

---

### Phase 9 - Testing and Validation
Goal: ensure that the system works reliably.

Planned testing areas:
- Unit tests for source adapters
- Unit tests for normalization logic
- Unit tests for duplicate detection
- API tests for search and alerts
- Background job tests
- Integration tests for ingestion pipeline

Validation goals:
- verify that jobs are fetched correctly
- verify that normalization is consistent
- verify that search returns relevant results
- verify that emails are triggered for matching alerts

Deliverable:
- Test suite covering major modules

---

### Phase 10 - Documentation, Demo, and Reporting
Goal: prepare the project for progress report, final report, and demo presentation.

Tasks:
- Document project setup
- Document API usage
- Prepare screenshots
- Prepare architecture diagram
- Prepare use case scenario
- Prepare demo scenario
- Update GitHub README
- Finalize report sections

Deliverable:
- Report-ready and demo-ready system

---

## 5. Planned Folder Structure

```text
project-root/
├── backend/
│   ├── config/
│   ├── apps/
│   │   ├── jobs/
│   │   ├── search/
│   │   ├── alerts/
│   │   ├── tracking/
│   │   └── users/
│   ├── requirements/
│   └── manage.py
├── docker/
├── docs/
├── .env
├── docker-compose.yml
└── README.md

---

## 6. Planned Background Jobs

The following scheduled tasks are planned:

### 1. Nightly Job Fetch Task
- Fetch jobs from external APIs
- Store raw records

### 2. Normalization Task
- Normalize raw records
- Deduplicate jobs
- Update searchable records

### 3. Embedding Task
- Generate embeddings for new jobs

### 4. Alert Task
- Match new jobs with user alerts
- Send email notifications

This separation improves maintainability and fault isolation.

---

## 7. Planned API Endpoints

Example initial endpoints:

- GET /api/jobs/
- GET /api/jobs/{id}/
- GET /api/jobs/search/
- POST /api/alerts/
- GET /api/alerts/
- POST /api/tracking/search/
- POST /api/tracking/click/

These endpoints may evolve during implementation.

---

## 8. Risks and Challenges

### 1. External API variability
Different sources may have different schemas, missing fields, rate limits, or pagination logic.

### 2. Data normalization difficulty
The same job concept may be represented differently across sources.

### 3. Duplicate detection
The same job posting may appear across multiple sources with slight differences.

### 4. Semantic search complexity
Embedding generation and ranking integration may increase implementation complexity.

### 5. Email delivery and scheduling
Alert processing requires reliable background job execution.

### 6. Personalization quality
Behavior-based ranking may need tuning to avoid noisy recommendations.

---

## 9. Future Improvements

The following are considered future work beyond the MVP:

- Add more job sources
- Add scraping-based adapters for sources without official APIs
- Add advanced analytics dashboard
- Add recruiter/company-based search filters
- Add saved jobs / favorites
- Add feedback loop using clicked email links
- Add RAG-based query reformulation and ranking enhancement

---

## 10. Minimum Viable Product (MVP)

The MVP will include:

- Dockerized Django setup
- PostgreSQL database
- API-based ingestion from 3 sources
- Job normalization
- Duplicate detection
- Keyword search
- Basic semantic search
- User registration/login
- Alert creation
- Email notification
- Interaction tracking

This MVP is sufficient to demonstrate the core value of the proposed system.

---

## 11. Expected Outcome

At the end of the project, the system is expected to provide:

- A unified searchable job database
- A normalized multi-source job dataset
- Semantic search support
- User alert functionality
- Personalized ranking signals based on user behavior

The final system will serve as a practical demonstration of how software engineering, information retrieval, and AI-supported semantic processing can be combined in a single application.