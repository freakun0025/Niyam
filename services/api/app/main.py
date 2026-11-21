"""FastAPI application factory and request middleware."""

import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.logging import configure_logging, log_event
from app.models.schemas import ErrorResponse
from app.routes import health, version

REQUEST_ID_HEADER = "X-Request-ID"
UNLOGGED_PATHS = frozenset({"/healthz", "/readyz"})


async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Assign a request ID, log the outcome, and return a safe error on failure."""
    request_id = str(uuid4())
    request.state.request_id = request_id
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
        log_event(
            "request.completed",
            **common,
            status=response.status_code,
            latency_ms={"total": total_ms},
        )
    return response


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application without changing global logging."""
    resolved = settings or get_settings()
    app = FastAPI(title="Niyam API", version=resolved.app_version)
    app.state.settings = resolved
    app.state.readiness_checks = {}
    app.middleware("http")(request_context)
    app.include_router(health.router)
    app.include_router(version.router)
    return app


def build_app() -> FastAPI:
    """Uvicorn entry point: configure JSON logging, then build the application."""
    settings = get_settings()
    configure_logging(settings)
    return create_app(settings)
