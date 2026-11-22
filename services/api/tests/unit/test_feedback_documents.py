import logging
from collections.abc import Iterator
from datetime import date
from typing import Any
from uuid import uuid1, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException

from app.config import Settings
from app.ingest.chunker import Chunk
from app.ingest.indexer import ensure_collection, store_document
from app.ingest.manifest import ManifestEntry
from app.main import create_app
from app.rag import retriever

COLLECTION = "circulars_test"

pytestmark = pytest.mark.filterwarnings("ignore:Payload indexes have no effect")


class FailingQdrant:
    def scroll(self, *args: Any, **kwargs: Any) -> None:
        raise ResponseHandlingException(ConnectionError("qdrant is down"))


def add_document(
    client: QdrantClient, doc_id: str, regulator: str, issued: date, chunks: int
) -> None:
    entry = ManifestEntry(
        doc_id=doc_id,
        file=f"raw/{doc_id}.pdf",
        title=f"Title of {doc_id}",
        regulator=regulator,
        doc_type="circular",
        issued_date=issued,
        source_url="https://www.example.org/source.pdf",
        sha256="a" * 64,
    )
    items = [Chunk(index, index + 1, f"Passage {index}") for index in range(chunks)]
    vectors = [[1.0, float(index), *([0.0] * 382)] for index in range(chunks)]
    store_document(client, COLLECTION, entry, items, vectors, "model", "run")


@pytest.fixture
def qdrant() -> Iterator[QdrantClient]:
    client = QdrantClient(":memory:")
    ensure_collection(client, COLLECTION)
    yield client
    client.close()


@pytest.fixture
def app(qdrant: QdrantClient) -> FastAPI:
    return create_app(Settings(qdrant_collection=COLLECTION), qdrant=qdrant)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def feedback_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "niyam_event", "") == "feedback.received"]


@pytest.mark.parametrize("rating", ["up", "down"])
def test_feedback_is_accepted_and_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture, rating: str
) -> None:
    answer_id = str(uuid4())

    with caplog.at_level(logging.INFO):
        response = client.post("/api/v1/feedback", json={"request_id": answer_id, "rating": rating})

    assert response.status_code == 202
    assert response.json() == {"ok": True}
    fields = feedback_records(caplog)[0].niyam_fields
    assert fields == {"request_id": answer_id, "rating": rating, "has_comment": False}


def test_feedback_comment_is_not_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        client.post(
            "/api/v1/feedback",
            json={"request_id": str(uuid4()), "rating": "down", "comment": "private remark"},
        )

    fields = feedback_records(caplog)[0].niyam_fields
    assert fields["has_comment"] is True
    assert "private remark" not in str(fields)


def test_blank_comment_counts_as_no_comment(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        client.post(
            "/api/v1/feedback",
            json={"request_id": str(uuid4()), "rating": "up", "comment": "   "},
        )

    assert feedback_records(caplog)[0].niyam_fields["has_comment"] is False


@pytest.mark.parametrize(
    "body",
    [
        {"request_id": "not-a-uuid", "rating": "up"},
        {"request_id": str(uuid1()), "rating": "up"},
        {"request_id": str(uuid4()), "rating": "sideways"},
        {"request_id": str(uuid4())},
        {"rating": "up"},
        {"request_id": str(uuid4()), "rating": "up", "comment": "x" * 501},
    ],
)
def test_invalid_feedback_is_rejected(client: TestClient, body: dict[str, Any]) -> None:
    response = client.post("/api/v1/feedback", json=body)

    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


def test_documents_are_grouped_and_sorted_newest_first(
    client: TestClient, qdrant: QdrantClient
) -> None:
    add_document(qdrant, "sebi-older", "SEBI", date(2023, 9, 20), 2)
    add_document(qdrant, "rbi-newest", "RBI", date(2025, 5, 8), 3)
    add_document(qdrant, "rbi-middle", "RBI", date(2024, 4, 15), 1)

    response = client.get("/api/v1/documents")

    assert response.status_code == 200
    assert response.json() == [
        {
            "doc_id": "rbi-newest",
            "title": "Title of rbi-newest",
            "regulator": "RBI",
            "issued_date": "2025-05-08",
            "chunks": 3,
        },
        {
            "doc_id": "rbi-middle",
            "title": "Title of rbi-middle",
            "regulator": "RBI",
            "issued_date": "2024-04-15",
            "chunks": 1,
        },
        {
            "doc_id": "sebi-older",
            "title": "Title of sebi-older",
            "regulator": "SEBI",
            "issued_date": "2023-09-20",
            "chunks": 2,
        },
    ]


def test_documents_counts_across_scroll_pages(
    client: TestClient, qdrant: QdrantClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(retriever, "DOCUMENT_SCROLL_PAGE_SIZE", 2)
    add_document(qdrant, "rbi-long-doc", "RBI", date(2025, 5, 8), 7)

    assert client.get("/api/v1/documents").json()[0]["chunks"] == 7


def test_empty_collection_returns_no_documents(client: TestClient) -> None:
    response = client.get("/api/v1/documents")

    assert response.status_code == 200
    assert response.json() == []


def test_documents_returns_503_when_qdrant_is_down(app: FastAPI, client: TestClient) -> None:
    app.state.qdrant = FailingQdrant()

    response = client.get("/api/v1/documents")

    assert response.status_code == 503
    assert response.json()["error"] == "vector_db_unavailable"
    assert "qdrant is down" not in response.text
