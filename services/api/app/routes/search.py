"""Search-only endpoint: returns matching passages without calling the LLM."""

from time import perf_counter

from fastapi import APIRouter, Request

from app.logging import question_log_fields
from app.models.schemas import ErrorResponse, Latency, SearchRequest, SearchResponse
from app.rag.retriever import retrieve, to_citations

router = APIRouter(prefix="/api/v1", tags=["search"])


def _ms(start: float, end: float) -> int:
    return round((end - start) * 1000)


@router.post(
    "/search",
    response_model=SearchResponse,
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def search(body: SearchRequest, request: Request) -> SearchResponse:
    state = request.app.state
    settings = state.settings

    started = perf_counter()
    vector = state.embedder.embed_query(body.question)
    embedded = perf_counter()
    hits = retrieve(state.qdrant, settings.qdrant_collection, vector, body.top_k, body.filters)
    finished = perf_counter()

    latency = Latency(
        embed=_ms(started, embedded),
        retrieve=_ms(embedded, finished),
        generate=0,
        total=_ms(started, finished),
    )
    request.state.log_fields = {
        **question_log_fields(body.question),
        "latency_ms": latency.model_dump(exclude={"total"}),
        "top_k": body.top_k,
        "hits": len(hits),
        "top_score": round(hits[0].score, 4) if hits else None,
    }
    return SearchResponse(
        request_id=request.state.request_id,
        hits=to_citations(hits),
        app_version=settings.app_version,
        latency_ms=latency,
    )
