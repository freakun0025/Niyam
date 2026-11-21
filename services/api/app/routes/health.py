"""Liveness and readiness probes."""

from collections.abc import Callable

from fastapi import APIRouter, Request, Response

from app.models.schemas import CheckStatus, HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])

# Only these can make a pod unready. Ollama is informational, so an LLM outage
# cannot remove every API pod from service.
REQUIRED_CHECKS = ("embedder", "qdrant")
INFO_CHECKS = ("ollama",)


def _run_check(check: Callable[[], bool] | None) -> CheckStatus:
    if check is None:
        return "not_configured"
    try:
        return "ok" if check() else "failed"
    except Exception:
        return "failed"


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse()


@router.get("/readyz", response_model=ReadyResponse, responses={503: {"model": ReadyResponse}})
def readyz(request: Request, response: Response) -> ReadyResponse:
    registered = request.app.state.readiness_checks
    checks = {name: _run_check(registered.get(name)) for name in (*REQUIRED_CHECKS, *INFO_CHECKS)}
    ready = all(checks[name] != "failed" for name in REQUIRED_CHECKS)
    if not ready:
        response.status_code = 503
    return ReadyResponse(ready=ready, checks=checks)
