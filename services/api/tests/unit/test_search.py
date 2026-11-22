import logging
from collections.abc import Iterator
from datetime import date
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException

from app import deps
from app.config import Settings
from app.ingest.chunker import Chunk
from app.ingest.indexer import ensure_collection, store_document
from app.ingest.manifest import ManifestEntry
from app.main import create_app
from app.rag.retriever import make_snippet

COLLECTION = "circulars_test"

pytestmark = pytest.mark.filterwarnings("ignore:Payload indexes have no effect")


def axis_vector(first: float, second: float) -> list[float]:
    return [first, second, *([0.0] * 382)]


class FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return axis_vector(1.0, 0.0)


class FailingQdrant:
    def query_points(self, *args: Any, **kwargs: Any) -> None:
        raise ResponseHandlingException(ConnectionError("qdrant is down"))


def entry(doc_id: str, regulator: str, issued: date) -> ManifestEntry:
    return ManifestEntry(
        doc_id=doc_id,
        file=f"raw/{doc_id}.pdf",
        title=f"Title of {doc_id}",
        regulator=regulator,
        doc_type="circular",
        circular_no=f"{regulator}/01",
        issued_date=issued,
        source_url="https://www.example.org/source.pdf",
        sha256="a" * 64,
    )


@pytest.fixture
def qdrant() -> Iterator[QdrantClient]:
    client = QdrantClient(":memory:")
    ensure_collection(client, COLLECTION)
    documents = [
        (entry("rbi-best-match", "RBI", date(2025, 5, 8)), 7, axis_vector(1.0, 0.0)),
        (entry("sebi-second-match", "SEBI", date(2023, 9, 20)), 2, axis_vector(0.8, 0.6)),
        (entry("rbi-third-match", "RBI", date(2020, 1, 15)), 4, axis_vector(0.1, 0.99)),
    ]
    for manifest_entry, page, vector in documents:
        chunk = Chunk(0, page, f"Passage from {manifest_entry.doc_id}. " + "detail " * 80)
        store_document(client, COLLECTION, manifest_entry, [chunk], [vector], "model", "run")
    yield client
    client.close()


@pytest.fixture
def app(qdrant: QdrantClient) -> FastAPI:
    settings = Settings(app_version="a1b2c3d", qdrant_collection=COLLECTION)
    return create_app(settings, embedder=FakeEmbedder(), qdrant=qdrant)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def post(client: TestClient, **body: Any) -> httpx.Response:
    return client.post("/api/v1/search", json={"question": "cooling-off period", **body})


def doc_ids(response: httpx.Response) -> list[str]:
    return [hit["doc_id"] for hit in response.json()["hits"]]


def test_search_returns_ranked_citations(client: TestClient) -> None:
    response = post(client)

    assert response.status_code == 200
    body = response.json()
    assert doc_ids(response) == ["rbi-best-match", "sebi-second-match", "rbi-third-match"]
    first = body["hits"][0]
    assert first["n"] == 1
    assert first["title"] == "Title of rbi-best-match"
    assert first["regulator"] == "RBI"
    assert first["circular_no"] == "RBI/01"
    assert first["issued_date"] == "2025-05-08"
    assert first["page"] == 7
    assert first["source_url"] == "https://www.example.org/source.pdf"
    assert first["score"] > body["hits"][1]["score"]
    assert body["app_version"] == "a1b2c3d"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["latency_ms"]["generate"] == 0


def test_top_k_limits_hits(client: TestClient) -> None:
    assert doc_ids(post(client, top_k=1)) == ["rbi-best-match"]


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"regulator": "SEBI"}, ["sebi-second-match"]),
        ({"regulator": "RBI"}, ["rbi-best-match", "rbi-third-match"]),
        ({"year_from": 2024}, ["rbi-best-match"]),
        ({"year_to": 2023}, ["sebi-second-match", "rbi-third-match"]),
        ({"year_from": 2021, "year_to": 2024}, ["sebi-second-match"]),
        ({"regulator": "RBI", "year_to": 2021}, ["rbi-third-match"]),
        ({"regulator": "SEBI", "year_from": 2024}, []),
        ({}, ["rbi-best-match", "sebi-second-match", "rbi-third-match"]),
    ],
)
def test_filters(client: TestClient, filters: dict[str, Any], expected: list[str]) -> None:
    assert doc_ids(post(client, filters=filters)) == expected


@pytest.mark.parametrize(
    "body",
    [
        {"question": "ab"},
        {"question": "    "},
        {"question": "x" * 501},
        {"top_k": 0},
        {"top_k": 9},
        {"filters": {"regulator": "NSE"}},
        {"filters": {"year_from": 1989}},
        {"filters": {"year_from": 2025, "year_to": 2020}},
    ],
)
def test_invalid_requests_return_the_error_contract(
    client: TestClient, body: dict[str, Any]
) -> None:
    response = post(client, **body)

    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_validation_error_does_not_echo_input(client: TestClient) -> None:
    response = client.post("/api/v1/search", json={"question": "x", "top_k": "private-value"})

    assert response.status_code == 422
    assert "private-value" not in response.text


def test_qdrant_failure_returns_503(app: FastAPI, client: TestClient) -> None:
    app.state.qdrant = FailingQdrant()

    response = post(client)

    assert response.status_code == 503
    assert response.json()["error"] == "vector_db_unavailable"
    assert "qdrant is down" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_search_logs_retrieval_fields(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    question = "cooling-off " * 30
    with caplog.at_level(logging.INFO):
        response = post(client, question=question)

    record = next(r for r in caplog.records if getattr(r, "niyam_event", "") == "request.completed")
    fields = record.niyam_fields
    assert fields["request_id"] == response.headers["X-Request-ID"]
    assert len(fields["question"]) == 200
    assert len(fields["question_hash"]) == 16
    assert fields["hits"] == 3
    assert fields["top_k"] == 4
    assert fields["top_score"] == pytest.approx(1.0, abs=0.001)
    assert {"embed", "retrieve", "generate", "total"} <= fields["latency_ms"].keys()


@pytest.mark.parametrize(
    ("text", "limit"),
    [("short text", 300), ("word " * 200, 300), ("x" * 1000, 300), ("word " * 20, 40)],
)
def test_snippets_respect_the_limit(text: str, limit: int) -> None:
    snippet = make_snippet(text, limit)

    assert len(snippet) <= limit
    if len(text) > limit:
        assert snippet.endswith("…")


def test_readiness_uses_qdrant_but_not_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_get(url: str, timeout: float) -> httpx.Response:
        calls.append(url)
        if "qdrant" in url:
            return httpx.Response(200)
        raise httpx.ConnectError("ollama is down")

    monkeypatch.setattr(deps.httpx, "get", fake_get)
    settings = Settings(qdrant_url="http://qdrant:6333/", ollama_url="http://ollama:11434")
    app = create_app(settings)
    app.state.readiness_checks.update(deps.build_readiness_checks(settings))

    response = TestClient(app).get("/readyz")

    assert response.status_code == 200
    assert response.json()["checks"] == {"embedder": "ok", "qdrant": "ok", "ollama": "failed"}
    assert "http://qdrant:6333/readyz" in calls
    assert "http://ollama:11434/api/version" in calls


def test_readiness_fails_when_qdrant_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, timeout: float) -> httpx.Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(deps.httpx, "get", fake_get)
    settings = Settings()
    app = create_app(settings)
    app.state.readiness_checks.update(deps.build_readiness_checks(settings))

    response = TestClient(app).get("/readyz")

    assert response.status_code == 503
    assert response.json()["checks"]["qdrant"] == "failed"
