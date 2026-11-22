"""Deployed version details, used by the UI footer and post-deploy checks."""

from fastapi import APIRouter, Request

from app.models.schemas import VersionResponse

router = APIRouter(tags=["version"])


@router.get("/version", response_model=VersionResponse)
def version(request: Request) -> VersionResponse:
    settings = request.app.state.settings
    return VersionResponse(
        app_version=settings.app_version,
        prompt_version=settings.prompt_version,
        embed_model=settings.embed_model,
        llm_model=settings.llm_model,
        collection=settings.qdrant_collection,
    )
