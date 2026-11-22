"""Builders for external clients and readiness checks."""

import warnings
from collections.abc import Callable

import httpx
from qdrant_client import QdrantClient

from app.config import Settings

QDRANT_TIMEOUT_SECONDS = 60
QDRANT_READY_TIMEOUT_SECONDS = 0.8
OLLAMA_READY_TIMEOUT_SECONDS = 0.5


def build_qdrant_client(settings: Settings) -> QdrantClient:
    """Create a Qdrant client using the injected API key when one exists."""
    with warnings.catch_warnings():
        # Traffic stays inside the cluster, and this warning would be a non-JSON log line.
        warnings.filterwarnings("ignore", message="Api key is used with an insecure connection")
        return QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.resolved_qdrant_api_key(),
            timeout=QDRANT_TIMEOUT_SECONDS,
            check_compatibility=False,
        )


def qdrant_ready(settings: Settings) -> bool:
    url = f"{settings.qdrant_url.rstrip('/')}/readyz"
    return httpx.get(url, timeout=QDRANT_READY_TIMEOUT_SECONDS).is_success


def ollama_reachable(settings: Settings) -> bool:
    url = f"{settings.ollama_url.rstrip('/')}/api/version"
    return httpx.get(url, timeout=OLLAMA_READY_TIMEOUT_SECONDS).is_success


def build_readiness_checks(settings: Settings) -> dict[str, Callable[[], bool]]:
    """The embedder is loaded before serving, so its check confirms startup completed."""
    return {
        "embedder": lambda: True,
        "qdrant": lambda: qdrant_ready(settings),
        "ollama": lambda: ollama_reachable(settings),
    }
