"""pgvector query helpers (cosine distance in PostgreSQL)."""

from typing import Any

from pgvector.django import CosineDistance


def cosine_distance_annotation(query_vector: list[float], *, field_name: str = "distance"):
    return {field_name: CosineDistance("embedding", query_vector)}


def distance_to_similarity(distance: float | None) -> float:
    """pgvector cosine distance is 1 - cosine_similarity for normalized vectors."""
    if distance is None:
        return 0.0
    return max(0.0, min(1.0, 1.0 - float(distance)))


def semantic_score_from_row(row: Any, *, distance_attr: str = "distance") -> float:
    return distance_to_similarity(getattr(row, distance_attr, None))
