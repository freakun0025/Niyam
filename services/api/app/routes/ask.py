"""Question answering endpoint."""

from fastapi import APIRouter, Request

from app.logging import question_log_fields
from app.models.schemas import AskRequest, AskResponse, ErrorResponse
from app.rag.pipeline import answer_question

router = APIRouter(prefix="/api/v1", tags=["ask"])


@router.post(
    "/ask",
    response_model=AskResponse,
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def ask(body: AskRequest, request: Request) -> AskResponse:
    state = request.app.state
    settings = state.settings
    request.state.log_fields = question_log_fields(body.question)

    result = answer_question(
        body.question, body.top_k, body.filters, settings, state.embedder, state.qdrant
    )

    request.state.log_fields.update(
        latency_ms=result.latency.model_dump(exclude={"total"}),
        top_k=body.top_k,
        hits=result.hits,
        top_score=result.top_score,
        refused=result.refused,
        refusal_reason=result.refusal_reason,
        model=result.model,
        prompt_version=settings.prompt_version,
        completion_tokens=result.completion_tokens,
    )
    return AskResponse(
        request_id=request.state.request_id,
        answer=result.answer,
        citations=result.citations,
        refused=result.refused,
        model=result.model,
        prompt_version=settings.prompt_version,
        app_version=settings.app_version,
        latency_ms=result.latency,
    )
