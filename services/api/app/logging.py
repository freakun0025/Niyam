"""Structured JSON logging to stdout (schema: DATA_MODEL section 4)."""

import json
import logging
import os
import socket
import sys
from datetime import UTC, datetime
from typing import Any

from app.config import Settings

SERVICE_NAME = "niyam-api"
GENERIC_EVENT = "app.log"

_EVENT_ATTR = "niyam_event"
_FIELDS_ATTR = "niyam_fields"
_BASE_KEYS = frozenset({"ts", "level", "service", "app_version", "pod", "event"})

logger = logging.getLogger("niyam")


def _timestamp(created: float) -> str:
    moment = datetime.fromtimestamp(created, tz=UTC)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class JsonFormatter(logging.Formatter):
    """Render each log record as one JSON object on one line."""

    def __init__(self, app_version: str, pod: str | None = None) -> None:
        super().__init__()
        self.app_version = app_version
        self.pod = pod or os.environ.get("HOSTNAME") or socket.gethostname()

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, _EVENT_ATTR, None)
        payload: dict[str, Any] = {
            "ts": _timestamp(record.created),
            "level": record.levelname,
            "service": SERVICE_NAME,
            "app_version": self.app_version,
            "pod": self.pod,
            "event": event or GENERIC_EVENT,
        }
        if event is None:
            payload["logger"] = record.name
            payload["message"] = record.getMessage()

        fields = getattr(record, _FIELDS_ATTR, {})
        payload.update({key: value for key, value in fields.items() if key not in _BASE_KEYS})

        if record.exc_info and record.exc_info[0] is not None:
            payload["error_type"] = record.exc_info[0].__name__
            payload["error_message"] = str(record.exc_info[1])
            payload["traceback"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))


def log_event(event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Emit a named application event with extra structured fields."""
    logger.log(level, event, extra={_EVENT_ATTR: event, _FIELDS_ATTR: fields})


def configure_logging(settings: Settings) -> None:
    """Send all application and uvicorn logs to stdout as JSON. Safe to call repeatedly."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(app_version=settings.app_version))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True

    # The request middleware writes request.completed, so uvicorn's access log stays off.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers = []
    access_logger.propagate = False
    access_logger.disabled = True
