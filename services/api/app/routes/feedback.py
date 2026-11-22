"""Thumbs up/down feedback, recorded as a log event for Kibana."""

from fastapi import APIRouter, status

from app.logging import log_event
from app.models.schemas import ErrorResponse, FeedbackRequest, FeedbackResponse

router = APIRouter(prefix="/api/v1", tags=["feedback"])


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={422: {"model": ErrorResponse}},
)
def feedback(body: FeedbackRequest) -> FeedbackResponse:
    # The comment is free text from users, so only its presence is logged.
    log_event(
        "feedback.received",
        request_id=str(body.request_id),
        rating=body.rating,
        has_comment=bool(body.comment),
    )
    return FeedbackResponse()
