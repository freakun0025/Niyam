"""Builders for external clients shared by the API and the ingest job."""

import warnings

from qdrant_client import QdrantClient

from app.config import Settings

QDRANT_TIMEOUT_SECONDS = 60


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
