import logging
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def app() -> FastAPI:
    return create_app(Settings(app_version="a1b2c3d", prompt_version="v7"))


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def events(caplog: pytest.LogCaptureFixture, name: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if getattr(record, "niyam_event", None) == name]


def test_healthz_reports_process_is_up(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_is_ready_before_dependencies_exist(client: TestClient) -> None:
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "ready": True,
        "checks": {
            "embedder": "not_configured",
            "qdrant": "not_configured",
            "ollama": "not_configured",
        },
    }


@pytest.mark.parametrize("dependency", ["embedder", "qdrant"])
def test_readyz_fails_when_required_dependency_fails(
    app: FastAPI, client: TestClient, dependency: str
) -> None:
    app.state.readiness_checks[dependency] = lambda: False

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["ready"] is False
    assert response.json()["checks"][dependency] == "failed"


def test_readyz_treats_a_raising_check_as_failed(app: FastAPI, client: TestClient) -> None:
    def unreachable() -> bool:
        raise ConnectionError("qdrant down")

    app.state.readiness_checks["qdrant"] = unreachable

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["checks"]["qdrant"] == "failed"


def test_readyz_ignores_ollama_failure(app: FastAPI, client: TestClient) -> None:
    app.state.readiness_checks.update(
        {"embedder": lambda: True, "qdrant": lambda: True, "ollama": lambda: False}
    )

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["checks"]["ollama"] == "failed"


def test_version_reports_deployed_release(client: TestClient) -> None:
    response = client.get("/version")

    assert response.status_code == 200
    body = response.json()
    assert body["app_version"] == "a1b2c3d"
    assert body["prompt_version"] == "v7"
    assert body["embed_model"] == "BAAI/bge-small-en-v1.5"
    assert body["llm_model"] == "qwen2.5:3b"
    assert body["collection"] == "circulars_v1"


def test_each_response_has_a_request_id(client: TestClient) -> None:
    first = client.get("/version").headers["X-Request-ID"]
    second = client.get("/version").headers["X-Request-ID"]

    assert UUID(first).version == 4
    assert first != second


def test_requests_are_logged_with_their_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        response = client.get("/version")

    record = events(caplog, "request.completed")[-1]
    assert record.niyam_fields["request_id"] == response.headers["X-Request-ID"]
    assert record.niyam_fields["method"] == "GET"
    assert record.niyam_fields["path"] == "/version"
    assert record.niyam_fields["status"] == 200
    assert record.niyam_fields["latency_ms"]["total"] >= 0


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_health_checks_are_not_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture, path: str
) -> None:
    with caplog.at_level(logging.INFO):
        client.get(path)

    assert events(caplog, "request.completed") == []


def test_unhandled_error_is_logged_but_not_leaked(
    app: FastAPI, client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    @app.get("/boom")
    def boom() -> None:
        raise ValueError("secret internal detail")

    with caplog.at_level(logging.INFO):
        response = client.get("/boom")

    body = response.json()
    assert response.status_code == 500
    assert body["error"] == "internal"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert "secret internal detail" not in response.text

    record = events(caplog, "request.failed")[-1]
    assert record.niyam_fields["request_id"] == body["request_id"]
    assert record.niyam_fields["error_type"] == "ValueError"
    assert record.niyam_fields["error_message"] == "secret internal detail"
