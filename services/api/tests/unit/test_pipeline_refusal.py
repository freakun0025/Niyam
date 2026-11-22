import logging
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.config import Settings
from app.ingest.chunker import Chunk
from app.ingest.indexer import ensure_collection, store_document
from app.ingest.manifest import ManifestEntry
from app.main import create_app
from app.models.schemas import AskRequest, SearchRequest
from app.rag import generator, pipeline
from app.rag.generator import Generation, LLMUnavailable, generate
from app.rag.pipeline import REFUSAL_MESSAGE

COLLECTION = "circulars_test"

pytestmark = pytest.mark.filterwarnings("ignore:Payload indexes have no effect")


def axis_vector(first: float, second: float) -> list[float]:
    return [first, second, *([0.0] * 382)]


class FakeEmbedder:
    def __init__(self) -> None:
        self.vector = axis_vector(1.0, 0.0)

    def embed_query(self, text: str) -> list[float]:
        return self.vector


@pytest.fixture
def qdrant() -> Iterator[QdrantClient]:
    client = QdrantClient(":memory:")
    ensure_collection(client, COLLECTION)
    for index, vector in enumerate([axis_vector(1.0, 0.0), axis_vector(0.9, 0.44)]):
        entry = ManifestEntry(
            doc_id=f"rbi-sample-{index}",
            file="raw/file.pdf",
            title=f"Circular {index}",
            regulator="RBI",
            doc_type="circular",
            issued_date=date(2025, 5, 8),
            source_url="https://www.example.org/source.pdf",
            sha256="a" * 64,
        )
        chunk = Chunk(0, index + 1, f"Source text number {index}. " * 8)
        store_document(client, COLLECTION, entry, [chunk], [vector], "model", "run")
    yield client
    client.close()


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def app(qdrant: QdrantClient, embedder: FakeEmbedder) -> FastAPI:
    settings = Settings(
        app_version="a1b2c3d",
        qdrant_collection=COLLECTION,
        refusal_threshold=0.7,
        llm_model="test-model",
    )
    return create_app(settings, embedder=embedder, qdrant=qdrant)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def llm(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], list[str]]:
    def configure(answer: str) -> list[str]:
        calls: list[str] = []

        def fake_generate(settings: Settings, system: str, user: str) -> Generation:
            calls.append(user)
            return Generation(text=answer, completion_tokens=12)

        monkeypatch.setattr(pipeline, "generate", fake_generate)
        return calls

    return configure


def ask(client: TestClient, **body: Any) -> httpx.Response:
    return client.post("/api/v1/ask", json={"question": "What is the period?", **body})


def test_supported_answer_returns_only_cited_sources(
    client: TestClient, llm: Callable[[str], list[str]]
) -> None:
    calls = llm("The period is one day [2].")

    response = ask(client)

    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is False
    assert body["answer"] == "The period is one day [2]."
    assert [citation["n"] for citation in body["citations"]] == [2]
    assert body["citations"][0]["doc_id"] == "rbi-sample-1"
    assert body["model"] == "test-model"
    assert body["prompt_version"] == "v1"
    assert body["app_version"] == "a1b2c3d"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert "[1] Circular 0" in calls[0]


def test_ask_uses_more_context_than_search_by_default() -> None:
    assert AskRequest(question="What is the period?").top_k == 6
    assert SearchRequest(question="What is the period?").top_k == 4


def test_low_score_refuses_without_calling_llm(
    client: TestClient, embedder: FakeEmbedder, llm: Callable[[str], list[str]]
) -> None:
    calls = llm("This must never be returned [1].")
    embedder.vector = axis_vector(0.0, 1.0)

    body = ask(client, top_k=1).json()

    assert calls == []
    assert body["refused"] is True
    assert body["answer"] == REFUSAL_MESSAGE
    assert body["citations"] == []
    assert body["model"] is None
    assert body["latency_ms"]["generate"] == 0


def test_filter_with_no_matches_refuses(
    client: TestClient, llm: Callable[[str], list[str]]
) -> None:
    calls = llm("This must never be returned [1].")

    body = ask(client, filters={"regulator": "SEBI"}).json()

    assert calls == []
    assert body["refused"] is True


@pytest.mark.parametrize(
    "answer",
    [
        "NOT_FOUND",
        "not_found",
        "NOT_FOUND. The sources do not say.",
        "An uncited claim about lending.",
        "A claim citing an invented source [9].",
        "",
    ],
)
def test_unsupported_llm_answers_become_refusals(
    client: TestClient, llm: Callable[[str], list[str]], answer: str
) -> None:
    llm(answer)

    body = ask(client).json()

    assert body["refused"] is True
    assert body["answer"] == REFUSAL_MESSAGE
    assert body["citations"] == []
    assert body["model"] is None


def test_invalid_citation_is_removed_from_supported_answer(
    client: TestClient, llm: Callable[[str], list[str]]
) -> None:
    llm("Valid fact [1]. Invented fact [7].")

    body = ask(client).json()

    assert body["answer"] == "Valid fact [1]. Invented fact."
    assert [citation["n"] for citation in body["citations"]] == [1]


def test_llm_failure_returns_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_generate(*args: Any) -> Generation:
        raise LLMUnavailable("connect")

    monkeypatch.setattr(pipeline, "generate", failing_generate)

    response = ask(client)

    assert response.status_code == 503
    assert response.json()["error"] == "llm_unavailable"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_search_still_works_when_llm_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_generate(*args: Any) -> Generation:
        raise LLMUnavailable("connect")

    monkeypatch.setattr(pipeline, "generate", failing_generate)

    response = client.post("/api/v1/search", json={"question": "What is the period?"})

    assert response.status_code == 200
    assert response.json()["hits"]


def test_ask_logs_refusal_details(
    client: TestClient,
    embedder: FakeEmbedder,
    llm: Callable[[str], list[str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm("unused")
    embedder.vector = axis_vector(0.0, 1.0)

    with caplog.at_level(logging.INFO):
        ask(client, top_k=1)

    record = next(r for r in caplog.records if getattr(r, "niyam_event", "") == "request.completed")
    fields = record.niyam_fields
    assert fields["refused"] is True
    assert fields["refusal_reason"] == "low_score"
    assert fields["prompt_version"] == "v1"
    assert fields["model"] is None
    assert fields["question_hash"]


def test_generator_sends_deterministic_capped_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, json: dict[str, Any], timeout: httpx.Timeout) -> httpx.Response:
        captured.update(url=url, json=json, timeout=timeout)
        request = httpx.Request("POST", url)
        body = {"message": {"content": "  Answer [1].  "}, "eval_count": 9}
        return httpx.Response(200, json=body, request=request)

    monkeypatch.setattr(generator.httpx, "post", fake_post)
    settings = Settings(ollama_url="http://ollama:11434/", llm_model="test-model")

    result = generate(settings, "system text", "user text")

    assert result == Generation("Answer [1].", 9)
    assert captured["url"] == "http://ollama:11434/api/chat"
    payload = captured["json"]
    assert payload["model"] == "test-model"
    assert payload["stream"] is False
    assert payload["options"] == {"num_predict": 256, "temperature": 0.1, "seed": 42}
    assert [message["role"] for message in payload["messages"]] == ["system", "user"]
    assert captured["timeout"].read == 60


@pytest.mark.parametrize(
    ("failure", "error_type"),
    [
        (httpx.ReadTimeout("slow"), "timeout"),
        (httpx.ConnectError("refused"), "connect"),
    ],
)
def test_generator_maps_transport_errors(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, error_type: str
) -> None:
    def fake_post(*args: Any, **kwargs: Any) -> httpx.Response:
        raise failure

    monkeypatch.setattr(generator.httpx, "post", fake_post)

    with pytest.raises(LLMUnavailable, match=error_type):
        generate(Settings(), "system", "user")


@pytest.mark.parametrize(
    "response_kwargs",
    [{"status_code": 500, "text": "error"}, {"status_code": 200, "json": {"unexpected": True}}],
)
def test_generator_maps_bad_responses(
    monkeypatch: pytest.MonkeyPatch, response_kwargs: dict[str, Any]
) -> None:
    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(request=httpx.Request("POST", url), **response_kwargs)

    monkeypatch.setattr(generator.httpx, "post", fake_post)

    with pytest.raises(LLMUnavailable, match="http"):
        generate(Settings(), "system", "user")
