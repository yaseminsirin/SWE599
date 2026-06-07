"""pgvector query helpers (cosine distance in PostgreSQL)."""

from contextlib import contextmanager
from typing import Any

from django.conf import settings
from django.db import connection

from pgvector.django import CosineDistance


def cosine_distance_annotation(query_vector: list[float], *, field_name: str = "distance"):
    return {field_name: CosineDistance("embedding", query_vector)}


def distance_to_similarity(distance: float | None) -> float:
    """pgvector cosine distance is 1 - cosine_similarity for normalized vectors."""
    if distance is None:
        return 0.0
    return max(0.0, min(1.0, 1.0 - float(distance)))


def semantic_score_from_row(row: Any, *, distance_attr: str = "distance") -> float:
    if isinstance(row, dict):
        return distance_to_similarity(row.get(distance_attr))
    return distance_to_similarity(getattr(row, distance_attr, None))


@contextmanager
def with_hnsw_ef_search(ef_search: int | None = None):
    """Lower ef_search speeds HNSW ANN at a small recall cost."""
    if connection.vendor != "postgresql":
        yield
        return
    value = ef_search or int(getattr(settings, "SEMANTIC_SEARCH_HNSW_EF_SEARCH", 40))
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL hnsw.ef_search = %s", [value])
    except Exception:
        pass
    yield
