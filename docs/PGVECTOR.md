# pgvector integration

## Docker rebuild (required after embedding provider change)

The stack uses `pgvector/pgvector:pg16` and **384-dimensional** vectors from
`sentence-transformers/all-MiniLM-L6-v2` (default).

```bash
docker compose build web worker beat
docker compose up -d db
docker compose exec web python manage.py migrate
docker compose exec web python manage.py regenerate_embeddings --relevant-only
```

If migrate fails on extension (old postgres image data), reset DB volume:

```bash
docker compose down
docker volume rm swe599_postgres_data   # name may vary: docker volume ls
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py regenerate_embeddings --relevant-only
```

## Embedding model (local, not an LLM)

| Setting | Default |
|---------|---------|
| `EMBEDDING_PROVIDER` | `sentence_transformers` |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` |
| `EMBEDDING_DIMENSION` | `384` |

The model is pre-downloaded during `docker compose build`. Vectors are stored in
`JobEmbedding.embedding` (`VectorField`) with an **HNSW** index for approximate
nearest-neighbor search.

Migration `0004_embedding_384_minilm` clears legacy **768-dim Gemini** vectors and
recreates indexes at 384 dimensions. Always run `regenerate_embeddings` after migrate.

## Regenerate embeddings

```bash
docker compose exec web python manage.py audit_embeddings
docker compose exec web python manage.py regenerate_embeddings --relevant-only
docker compose exec web python manage.py regenerate_embeddings --source adzuna --limit 500
```

Or via Celery:

```bash
docker compose exec web python manage.py shell -c \
  "from apps.search.tasks import regenerate_all_embeddings_task; print(regenerate_all_embeddings_task())"
```

## Verify pgvector

```bash
docker compose exec db psql -U jobs_user -d jobs_db -c \
  "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"

docker compose exec web python manage.py test apps.search.tests.test_pgvector -v2
docker compose exec web python manage.py test apps.search.tests.test_sentence_transformer_embeddings -v2
```

If tests fail with `collation version mismatch` after switching the DB image:

```bash
docker compose exec db psql -U jobs_user -d jobs_db -c \
  "ALTER DATABASE template1 REFRESH COLLATION VERSION; ALTER DATABASE postgres REFRESH COLLATION VERSION; ALTER DATABASE jobs_db REFRESH COLLATION VERSION;"
```

## Known limitations

- `EMBEDDING_DIMENSION` must match `VectorField` (default **384** with MiniLM).
- Tests require **PostgreSQL** (no SQLite fallback).
- **Do not mix** Gemini, hash-fallback, and sentence-transformer vectors in the same active index.
- `EMBEDDING_STRICT_PROVIDER=true` (default) prevents silent fallback to hash embeddings.
- Optional Gemini embeddings (`EMBEDDING_PROVIDER=gemini`, 768-dim) require migration and full regen if switched.
- HNSW index helps at scale; very small datasets work without tuning `ef_search`.
