"""FastAPI application factory and request middleware."""

import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.deps import build_qdrant_client, build_readiness_checks
from app.logging import configure_logging, log_event
from app.models.schemas import ErrorResponse
from app.rag.embedder import Embedder
from app.rag.generator import LLMUnavailable
from app.rag.retriever import VectorDbUnavailable
from app.routes import ask, health, search, version

REQUEST_ID_HEADER = "X-Request-ID"
UNLOGGED_PATHS = frozenset({"/healthz", "/readyz"})


async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Assign a request ID, log the outcome, and return a safe error on failure."""
    request_id = str(uuid4())
    request.state.request_id = request_id
    request.state.log_fields = {}
    started = perf_counter()
    common = {"request_id": request_id, "method": request.method, "path": request.url.path}

    try:
        response = await call_next(request)
    except Exception as exc:
        log_event(
            "request.failed",
            logging.ERROR,
            **common,
            status=500,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        body = ErrorResponse(
            request_id=request_id, error="internal", detail="Internal server error"
        )
        return JSONResponse(
            status_code=500,
            content=body.model_dump(),
            headers={REQUEST_ID_HEADER: request_id},
        )

    response.headers[REQUEST_ID_HEADER] = request_id
    if request.url.path not in UNLOGGED_PATHS:
        total_ms = round((perf_counter() - started) * 1000)
        fields = dict(request.state.log_fields)
        latency = {**fields.pop("latency_ms", {}), "total": total_ms}
        log_event(
            "request.completed",
            **common,
            status=response.status_code,
            latency_ms=latency,
            **fields,
        )
    return response


def _error_response(request: Request, status: int, error: str, detail: str) -> JSONResponse:
    body = ErrorResponse(request_id=request.state.request_id, error=error, detail=detail)
    return JSONResponse(status_code=status, content=body.model_dump())


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Describe invalid fields without echoing the submitted values."""
    problems = [
        f"{'.'.join(str(part) for part in error['loc'] if part != 'body')}: {error['msg']}"
        for error in exc.errors()
    ]
    return _error_response(request, 422, "validation_error", "; ".join(problems))


async def handle_vector_db_unavailable(request: Request, exc: VectorDbUnavailable) -> JSONResponse:
    request.state.log_fields["error_type"] = "vector_db_unavailable"
    return _error_response(
        request, 503, "vector_db_unavailable", "The search index is temporarily unavailable."
    )


async def handle_llm_unavailable(request: Request, exc: LLMUnavailable) -> JSONResponse:
    request.state.log_fields["error_type"] = f"llm_{exc}"
    return _error_response(
        request,
        503,
        "llm_unavailable",
        "The answer service is temporarily unavailable. Source search still works.",
    )


def create_app(
    settings: Settings | None = None, embedder: Any = None, qdrant: Any = None
) -> FastAPI:
    """Build the application without changing global logging."""
    resolved = settings or get_settings()
    app = FastAPI(title="Niyam API", version=resolved.app_version)
    app.state.settings = resolved
    app.state.embedder = embedder
    app.state.qdrant = qdrant
    app.state.readiness_checks = {}
    app.middleware("http")(request_context)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(VectorDbUnavailable, handle_vector_db_unavailable)
    app.add_exception_handler(LLMUnavailable, handle_llm_unavailable)
    app.include_router(health.router)
    app.include_router(version.router)
    app.include_router(search.router)
    app.include_router(ask.router)
    return app


def build_app() -> FastAPI:
    """Uvicorn entry point: configure logging, load the model, then build the application."""
    settings = get_settings()
    configure_logging(settings)
    embedder = Embedder(
        settings.embed_model,
        settings.embed_cache,
        offline=settings.embed_offline,
        threads=settings.embed_threads,
    )
    app = create_app(settings, embedder=embedder, qdrant=build_qdrant_client(settings))
    app.state.readiness_checks.update(build_readiness_checks(settings))
    return app
