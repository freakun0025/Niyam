"""Pydantic models for the HTTP API (contract: DATA_MODEL section 3)."""

from typing import Literal

from pydantic import BaseModel

CheckStatus = Literal["ok", "failed", "not_configured"]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    ready: bool
    checks: dict[str, CheckStatus]


class VersionResponse(BaseModel):
    app_version: str
    prompt_version: str
    embed_model: str
    llm_model: str
    collection: str


class ErrorResponse(BaseModel):
    request_id: str
    error: Literal["validation_error", "llm_unavailable", "vector_db_unavailable", "internal"]
    detail: str
