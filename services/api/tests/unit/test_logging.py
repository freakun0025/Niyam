import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.logging import JsonFormatter, configure_logging, log_event


@pytest.fixture
def captured() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(app_version="a1b2c3d", pod="niyam-api-test"))
    root = logging.getLogger()
    old_handlers, old_level = root.handlers[:], root.level
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    yield stream
    root.handlers, root.level = old_handlers, old_level


def last_line(stream: io.StringIO) -> dict[str, Any]:
    return json.loads(stream.getvalue().strip().splitlines()[-1])


def test_event_has_required_schema_fields(captured: io.StringIO) -> None:
    log_event("request.completed", method="GET", path="/version", status=200)

    line = last_line(captured)

    assert line["ts"].endswith("Z")
    assert line["level"] == "INFO"
    assert line["service"] == "niyam-api"
    assert line["app_version"] == "a1b2c3d"
    assert line["pod"] == "niyam-api-test"
    assert line["event"] == "request.completed"
    assert (line["method"], line["path"], line["status"]) == ("GET", "/version", 200)


def test_event_fields_cannot_overwrite_base_fields(captured: io.StringIO) -> None:
    log_event("feedback.received", app_version="spoofed", service="spoofed", rating="up")

    line = last_line(captured)

    assert line["app_version"] == "a1b2c3d"
    assert line["service"] == "niyam-api"
    assert line["rating"] == "up"


def test_plain_library_logs_are_still_json(captured: io.StringIO) -> None:
    logging.getLogger("some.library").warning("disk %s", "slow")

    line = last_line(captured)

    assert line["event"] == "app.log"
    assert line["level"] == "WARNING"
    assert line["logger"] == "some.library"
    assert line["message"] == "disk slow"


def test_exception_stays_on_one_json_line(captured: io.StringIO) -> None:
    try:
        raise ValueError("bad value")
    except ValueError:
        logging.getLogger("niyam").exception("failed")

    assert len(captured.getvalue().strip().splitlines()) == 1
    line = last_line(captured)
    assert line["error_type"] == "ValueError"
    assert line["error_message"] == "bad value"
    assert "Traceback" in line["traceback"]


def test_unserializable_values_do_not_break_logging(captured: io.StringIO) -> None:
    log_event("ingest.completed", manifest=Path("data/manifest.yaml"))

    assert last_line(captured)["manifest"].endswith("manifest.yaml")


def test_configure_logging_is_idempotent_and_routes_uvicorn() -> None:
    root = logging.getLogger()
    old_handlers, old_level = root.handlers[:], root.level
    try:
        settings = Settings(app_version="a1b2c3d", log_level="WARNING")
        configure_logging(settings)
        configure_logging(settings)

        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
        assert root.level == logging.WARNING
        assert logging.getLogger("uvicorn.error").propagate is True
        assert logging.getLogger("uvicorn.access").disabled is True
    finally:
        root.handlers, root.level = old_handlers, old_level
        logging.getLogger("uvicorn.access").disabled = False
