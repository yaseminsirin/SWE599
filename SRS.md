# Software Requirements Specification (SRS)

This document defines the requirements for the Job Aggregation and Intelligent Search System.  
The system collects job postings from multiple sources, normalizes them into a unified schema, supports keyword and semantic search, and provides intelligent personalized job alerts using RAG-based email generation.

---

# Feature 1 - Job Data Collection (Multi-Source Ingestion)

## Description
This feature is responsible for collecting job postings from multiple external sources (Adzuna, USAJOBS, Remotive) via APIs. The system periodically fetches job listings and stores raw data for further processing.

## User Story
> As a system, I want to collect job postings from multiple sources so that users can access a unified job database.

## Acceptance Criteria
- Given scheduled execution, the system shall fetch job data from all configured sources.
- Given API response, the system shall store raw job data.
- Given API failure, the system shall retry or log the error.

## Functional Requirements

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-01a | The system shall fetch job postings from Adzuna API. | High | |
| FR-01b | The system shall fetch job postings from USAJOBS API. | High | |
| FR-01c | The system shall fetch job postings from Remotive API. | High | |
| FR-01d | The system shall store raw API responses before processing. | High | |
| FR-01e | The system shall support scheduled execution for periodic ingestion. | High | Cron Job |
| FR-01f | The system shall support background jobs for ingestion and alert processing. | High | |
| FR-01g | The system shall support separate background tasks for data fetching and email notifications. | High | |

## Nonfunctional Requirements

| ID | Type | Description | Priority |
|---|---|---|---|
| NFR-01a | Reliability | Data fetching shall retry on temporary failures. | High |
| NFR-01b | Performance | Data ingestion shall complete within scheduled batch time. | Medium |

---

# Feature 2 - Job Normalization & Deduplication

## Description
This feature converts heterogeneous job data from different sources into a unified internal schema and removes duplicate job postings.

## User Story
> As a system, I want to normalize and deduplicate job data so that all job postings can be searched and compared consistently.

## Acceptance Criteria
- Given raw job data, the system shall map it into a unified schema.
- Given inconsistent formats, the system shall standardize them.
- Given duplicate job postings, the system shall merge or ignore duplicates.

## Functional Requirements

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-02a | The system shall map external job data into a unified JobPosting schema. | High | |
| FR-02b | The system shall normalize job titles into a standard format. | High | |
| FR-02c | The system shall normalize employment types into predefined categories. | High | |
| FR-02d | The system shall normalize location data. | High | |
| FR-02e | The system shall normalize salary data into min/max/currency format. | Medium | |
| FR-02f | The system shall clean and store job descriptions. | High | |
| FR-02g | The system shall generate content hashes for duplicate detection. | High | |
| FR-02h | The system shall detect and merge duplicate job postings from different sources. | High | |

## Nonfunctional Requirements

| ID | Type | Description | Priority |
|---|---|---|---|
| NFR-02a | Consistency | Normalized data shall follow a unified schema. | High |
| NFR-02b | Reliability | Normalization shall not corrupt original data. | High |

---

# Feature 3 - Keyword-Based Job Search

## Description
This feature allows users to search job postings using keywords and filters.

## User Story
> As a user, I want to search job listings so that I can find relevant job opportunities.

## Acceptance Criteria
- Given a search query, the system shall return matching jobs.
- Given filters, results shall be filtered accordingly.

## Functional Requirements

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-03a | The system shall support keyword-based search. | High | |
| FR-03b | The system shall allow filtering by location. | High | |
| FR-03c | The system shall allow filtering by employment type. | Medium | |
| FR-03d | The system shall allow filtering by remote jobs. | Medium | |

## Nonfunctional Requirements

| ID | Type | Description | Priority |
|---|---|---|---|
| NFR-03a | Performance | Search results shall be returned within 2 seconds. | High |
| NFR-03b | Usability | Search interface shall be simple and intuitive. | Medium |

---

# Feature 4 - Semantic Search (Embedding-Based Retrieval)

## Description
This feature enables semantic job search using embeddings, vector storage, and cosine similarity.

Normalized job postings are converted into embeddings and stored in a vector database. User queries are also converted into embeddings, and the system retrieves the most semantically relevant job postings using similarity search.

## User Story
> As a user, I want to find jobs similar to my query even if exact keywords do not match.

## Acceptance Criteria
- Given a query, the system shall compute embeddings.
- Given stored embeddings, the system shall calculate similarity scores.
- Given semantic retrieval, the system shall rank relevant jobs.

## Functional Requirements

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-04a | The system shall generate embeddings for job descriptions. | High | |
| FR-04b | The system shall compute cosine similarity between user queries and job embeddings. | High | |
| FR-04c | The system shall rank jobs based on semantic similarity scores. | High | |
| FR-04d | The system shall store job embeddings in a vector database for semantic retrieval. | High | |
| FR-04e | The system may support LLM-based query enhancement in future improvements. | Medium | |
| FR-04f | The system shall support hybrid retrieval using keyword filtering and semantic similarity together. | High | |

## Semantic Retrieval Flow
1. Job postings are normalized.
2. Embeddings are generated for each job posting.
3. Embeddings are stored in the vector database.
4. User query is converted into an embedding.
5. Cosine similarity search retrieves the most relevant jobs.
6. Keyword-based filters may further refine results.

## Nonfunctional Requirements

| ID | Type | Description | Priority |
|---|---|---|---|
| NFR-04a | Performance | Semantic search shall return results within 3 seconds. | Medium |
| NFR-04b | Accuracy | Semantic retrieval shall improve relevance over keyword search. | High |

---

# Feature 5 - Job Alerts (Email Notifications)

## Description
This feature allows users to create alerts and receive email notifications when new jobs match their criteria.

## User Story
> As a user, I want to receive job alerts so that I do not miss new opportunities.

## Acceptance Criteria
- Given alert preferences, the system shall store user criteria.
- Given new matching jobs, the system shall notify users.

## Functional Requirements

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-05a | Users shall be able to create job alerts with queries and filters. | High | |
| FR-05b | The system shall send email notifications for matching jobs. | High | |
| FR-05c | The system shall send top matching jobs in alert emails. | High | |

## Nonfunctional Requirements

| ID | Type | Description | Priority |
|---|---|---|---|
| NFR-05a | Reliability | Emails shall be delivered successfully. | High |
| NFR-05b | Performance | Email jobs shall execute asynchronously. | High |

---

# Feature 6 - User Interaction Tracking

## Description
This feature tracks user clicks, searches, and email interactions to improve ranking quality.

## User Story
> As a system, I want to track user behavior so that I can improve search relevance and recommendations.

## Acceptance Criteria
- Given a user clicks a job posting, the system shall record the interaction.
- Given a user performs a search, the system shall store the query.
- Given a user clicks a job link inside an email alert, the system shall record the interaction.

## Functional Requirements

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-06a | The system shall record job click events. | High | |
| FR-06b | The system shall record user search queries. | High | |
| FR-06c | The system shall store ranking positions of clicked jobs. | Medium | |
| FR-06d | The system shall track clicks on job links included in email alerts. | High | |

## Nonfunctional Requirements

| ID | Type | Description | Priority |
|---|---|---|---|
| NFR-06a | Privacy | User interaction data shall be stored securely. | High |
| NFR-06b | Performance | Tracking operations shall not affect user experience. | High |

---

# Feature 7 - Personalized Ranking & Recommendation

## Description
This feature improves search results using semantic similarity, user behavior, and interaction signals collected from searches and email clicks.

## User Story
> As a user, I want better ranked results so that I can find the most relevant jobs quickly.

## Acceptance Criteria
- Given interaction history, the system shall improve result ranking.
- Given user clicks, similar jobs shall rank higher.

## Functional Requirements

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-07a | The system shall weight search results based on user clicks. | High | |
| FR-07b | The system shall use embeddings to recommend similar jobs. | High | |
| FR-07c | The system may support future ranking improvements using additional behavioral signals. | Medium | |
| FR-07d | The system shall use tracked email click interactions as ranking signals. | High | |

## Nonfunctional Requirements

| ID | Type | Description | Priority |
|---|---|---|---|
| NFR-07a | Performance | Ranking operations shall not significantly increase response time. | High |
| NFR-07b | Scalability | The system shall support growing data volume. | Medium |

---

# Feature 8 - RAG-Based Email Content Generation

## Description
This feature uses Retrieval-Augmented Generation (RAG) to generate understandable and personalized email alerts.

After semantic retrieval identifies the most relevant job postings, the retrieved job results are provided to an LLM as contextual information. The LLM generates summarized and user-friendly email content explaining why the jobs may match the user’s interests.

## User Story
> As a user, I want job alerts to include meaningful summaries and explanations so that I can quickly understand why jobs are relevant to me.

## Acceptance Criteria
- Given retrieved job results, the system shall provide them as context to the LLM.
- Given contextual job data, the system shall generate summarized email content.
- Given generated content, the system shall include it in alert emails.

## Functional Requirements

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-08a | The system shall use retrieved job postings as context for LLM generation. | High | |
| FR-08b | The system shall generate summarized and explainable email content using RAG. | High | |
| FR-08c | The system shall include generated summaries in alert emails. | High | |
| FR-08d | The system shall support future personalization improvements for generated explanations. | Medium | |

## Nonfunctional Requirements

| ID | Type | Description | Priority |
|---|---|---|---|
| NFR-08a | Usability | Generated summaries shall be easy to understand. | High |
| NFR-08b | Performance | Email generation shall complete within acceptable processing time. | Medium |

---

# Feature 9 - System Overview

## Description
This feature describes the high-level architecture and workflow of the system.

## Components
- Data Ingestion Layer
- Normalization Layer
- Storage Layer
- Vector Database Layer
- Search Layer
- Alert System
- RAG-based Email Generation Layer
- User Interaction Tracking Layer

## Data Flow
1. External APIs provide job data.
2. Job postings are normalized and deduplicated.
3. Embeddings are generated and stored in the vector database.
4. Users perform keyword and semantic search queries.
5. Semantic retrieval identifies the most relevant jobs.
6. Retrieved jobs may be provided to the LLM for RAG-based email generation.
7. Alert emails are generated and sent to users.
8. User interactions and email clicks are recorded.
9. Interaction signals are used for ranking improvements.

---

# Feature 10 - API Layer

## Description
This feature provides REST API endpoints for job search, alerts, tracking, and job retrieval operations.

## User Story
> As a frontend client, I want to access job data through APIs so that I can display results to users.

## Functional Requirements

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-10a | The system shall provide API endpoints for job search. | High | |
| FR-10b | The system shall provide API endpoints for job details. | High | |
| FR-10c | The system shall provide API endpoints for job alerts. | High | |
| FR-10d | The system shall provide API endpoints for tracking user interactions. | High | |

## Nonfunctional Requirements

| ID | Type | Description | Priority |
|---|---|---|---|
| NFR-10a | Performance | API responses shall be returned within acceptable response times. | High |
| NFR-10b | Security | Public read/search APIs shall be open; alert and tracking writes shall not require login. | Medium |

---

# Feature 11 - Anonymous Usage (No Login)

## Description
The demo application does not require registration or login. Job search, alerts, and interaction tracking are available without authentication. Optional email addresses on alerts support notification delivery.

## Functional Requirements

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-11a | The system shall allow anonymous access to search and job listing APIs. | High | |
| FR-11b | The system shall allow creating and managing job alerts without login. | High | Shared alert list in demo UI |
| FR-11c | Alerts may store an optional `notify_email` for email delivery. | Medium | Falls back to `ALERT_DEFAULT_EMAIL` env |

## Nonfunctional Requirements

| ID | Type | Description | Priority |
|---|---|---|---|
| NFR-11a | Privacy | Interaction tracking shall not require personal accounts. | Medium |

---

# Glossary

| Term | Definition |
|---|---|
| Job Aggregation | Collecting job postings from multiple sources |
| Normalization | Converting heterogeneous job data into a unified schema |
| Semantic Search | Search based on meaning using embeddings |
| Vector Database | Database optimized for storing and retrieving embeddings |
| Cosine Similarity | Similarity metric used between vectors |
| RAG | Retrieval-Augmented Generation using retrieved context with LLMs |
| Job Alert | Email notification system for matching jobs |