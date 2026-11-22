"""Vector search over indexed circular chunks."""

from collections.abc import Sequence
from dataclasses import dataclass

import httpx
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.models.schemas import Citation, Filters

SNIPPET_MAX_CHARS = 300


class VectorDbUnavailable(RuntimeError):
    """Qdrant could not answer a search."""


@dataclass(frozen=True)
class Hit:
    score: float
    doc_id: str
    title: str
    regulator: str
    circular_no: str | None
    issued_date: str
    page: int
    text: str
    source_url: str


def build_filter(filters: Filters | None) -> models.Filter | None:
    if filters is None:
        return None

    conditions: list[models.FieldCondition] = []
    if filters.regulator is not None:
        conditions.append(
            models.FieldCondition(key="regulator", match=models.MatchValue(value=filters.regulator))
        )
    if filters.year_from is not None or filters.year_to is not None:
        conditions.append(
            models.FieldCondition(
                key="issued_year",
                range=models.Range(gte=filters.year_from, lte=filters.year_to),
            )
        )
    return models.Filter(must=conditions) if conditions else None


def retrieve(
    client: QdrantClient,
    collection: str,
    vector: Sequence[float],
    top_k: int,
    filters: Filters | None = None,
) -> list[Hit]:
    """Return the closest chunks, best match first."""
    try:
        points = client.query_points(
            collection,
            query=list(vector),
            query_filter=build_filter(filters),
            limit=top_k,
            with_payload=True,
        ).points
    except (ResponseHandlingException, UnexpectedResponse, httpx.HTTPError, OSError) as exc:
        raise VectorDbUnavailable(str(exc)) from exc

    return [
        Hit(
            score=point.score,
            doc_id=point.payload["doc_id"],
            title=point.payload["title"],
            regulator=point.payload["regulator"],
            circular_no=point.payload.get("circular_no"),
            issued_date=point.payload["issued_date"],
            page=point.payload["page_start"],
            text=point.payload["text"],
            source_url=point.payload["source_url"],
        )
        for point in points
    ]


def make_snippet(text: str, limit: int = SNIPPET_MAX_CHARS) -> str:
    """Shorten text at a word boundary, keeping the ellipsis inside the limit."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    word_end = cut.rfind(" ")
    if word_end > limit // 2:
        cut = cut[:word_end]
    return f"{cut.rstrip()}…"


def to_citations(hits: Sequence[Hit]) -> list[Citation]:
    return [
        Citation(
            n=number,
            doc_id=hit.doc_id,
            title=hit.title,
            regulator=hit.regulator,
            circular_no=hit.circular_no,
            issued_date=hit.issued_date,
            page=hit.page,
            snippet=make_snippet(hit.text),
            source_url=hit.source_url,
            score=round(hit.score, 4),
        )
        for number, hit in enumerate(hits, start=1)
    ]
