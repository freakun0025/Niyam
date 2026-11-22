"""List the circulars currently available for search."""

from fastapi import APIRouter, Request

from app.models.schemas import DocumentInfo, ErrorResponse
from app.rag.retriever import list_documents

router = APIRouter(prefix="/api/v1", tags=["documents"])


@router.get(
    "/documents",
    response_model=list[DocumentInfo],
    responses={503: {"model": ErrorResponse}},
)
def documents(request: Request) -> list[DocumentInfo]:
    state = request.app.state
    return list_documents(state.qdrant, state.settings.qdrant_collection)
