"""Pydantic models for the HTTP API (contract: DATA_MODEL section 3)."""

from datetime import date
from typing import Literal

from pydantic import UUID4, BaseModel, ConfigDict, Field, HttpUrl, model_validator

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


class Filters(BaseModel):
    regulator: Literal["RBI", "SEBI"] | None = None
    year_from: int | None = Field(None, ge=1990, le=2100)
    year_to: int | None = Field(None, ge=1990, le=2100)

    @model_validator(mode="after")
    def year_range_is_ordered(self) -> "Filters":
        if self.year_from is not None and self.year_to is not None:
            if self.year_from > self.year_to:
                raise ValueError("year_from cannot be after year_to")
        return self


class SearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=3, max_length=500)
    top_k: int = Field(4, ge=1, le=8)
    filters: Filters | None = None


class Citation(BaseModel):
    n: int
    doc_id: str
    title: str
    regulator: str
    circular_no: str | None
    issued_date: date
    page: int
    snippet: str = Field(max_length=300)
    source_url: HttpUrl
    score: float


class Latency(BaseModel):
    embed: int
    retrieve: int
    generate: int
    total: int


class SearchResponse(BaseModel):
    request_id: str
    hits: list[Citation]
    app_version: str
    latency_ms: Latency


class AskRequest(SearchRequest):
    top_k: int = Field(6, ge=1, le=8)  # More context measurably improves generated answers.


class AskResponse(BaseModel):
    request_id: str
    answer: str
    citations: list[Citation]
    refused: bool
    model: str | None
    prompt_version: str
    app_version: str
    latency_ms: Latency


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    request_id: UUID4
    rating: Literal["up", "down"]
    comment: str | None = Field(None, max_length=500)


class FeedbackResponse(BaseModel):
    ok: Literal[True] = True


class DocumentInfo(BaseModel):
    doc_id: str
    title: str
    regulator: str
    issued_date: date
    chunks: int
