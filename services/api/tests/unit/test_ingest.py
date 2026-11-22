import hashlib
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from uuid import UUID

import pytest
import yaml
from qdrant_client import QdrantClient

from app.config import Settings
from app.ingest.cli import run_ingest
from app.ingest.indexer import IndexerError, ensure_collection, point_id
from app.ingest.manifest import ManifestError

COLLECTION = "circulars_test"
LONG = "Regulated entities shall disclose every charge to the borrower before lending. " * 16

pytestmark = pytest.mark.filterwarnings("ignore:Payload indexes have no effect")


class FakeEmbedder:
    def __init__(self) -> None:
        self.embedded = 0

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        self.embedded += len(texts)
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vectors.append([(digest[index % 32] + 1) / 256 for index in range(384)])
        return vectors


@pytest.fixture
def client() -> Iterator[QdrantClient]:
    qdrant = QdrantClient(":memory:")
    yield qdrant
    qdrant.close()


@pytest.fixture
def settings() -> Settings:
    return Settings(app_version="a1b2c3d", qdrant_collection=COLLECTION)


@pytest.fixture
def write_corpus(tmp_path: Path, make_pdf: Callable[..., Path]) -> Callable[..., Path]:
    def _write(documents: dict[str, list[str]]) -> Path:
        entries = []
        for doc_id, pages in documents.items():
            pdf = make_pdf(pages, f"raw/{doc_id}.pdf")
            entries.append(
                {
                    "doc_id": doc_id,
                    "file": f"raw/{doc_id}.pdf",
                    "title": f"Title of {doc_id}",
                    "regulator": "RBI",
                    "doc_type": "circular",
                    "circular_no": "RBI/2025-26/01",
                    "issued_date": "2025-05-08",
                    "source_url": "https://www.rbi.org.in/sample.pdf",
                    "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                }
            )
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(yaml.safe_dump({"version": 1, "documents": entries}), "utf-8")
        return manifest

    return _write


def stored(client: QdrantClient) -> int:
    return client.count(COLLECTION, exact=True).count


def test_point_ids_are_stable_uuids() -> None:
    assert point_id("rbi-sample", 3) == point_id("rbi-sample", 3)
    assert point_id("rbi-sample", 3) != point_id("rbi-sample", 4)
    assert UUID(point_id("rbi-sample", 3)).version == 5


def test_documents_are_indexed_with_citation_payload(
    client: QdrantClient, settings: Settings, write_corpus: Callable[..., Path]
) -> None:
    manifest = write_corpus({"rbi-sample": [LONG, LONG]})

    summary = run_ingest(manifest, client, FakeEmbedder(), settings)

    assert summary.docs_indexed == 1
    assert stored(client) == summary.chunks_total > 1
    payload = client.scroll(COLLECTION, limit=1)[0][0].payload
    assert payload["doc_id"] == "rbi-sample"
    assert payload["page_start"] == payload["page_end"]
    assert payload["regulator"] == "RBI"
    assert payload["issued_year"] == 2025
    assert payload["source_url"] == "https://www.rbi.org.in/sample.pdf"
    assert payload["embed_model"] == settings.embed_model
    assert payload["ingest_run_id"].startswith("a1b2c3d-")


def test_rerun_creates_no_duplicates_and_skips_embedding(
    client: QdrantClient, settings: Settings, write_corpus: Callable[..., Path]
) -> None:
    manifest = write_corpus({"rbi-sample": [LONG]})
    run_ingest(manifest, client, FakeEmbedder(), settings)
    count = stored(client)
    embedder = FakeEmbedder()

    summary = run_ingest(manifest, client, embedder, settings)

    assert (summary.docs_indexed, summary.docs_skipped) == (0, 1)
    assert embedder.embedded == 0
    assert stored(client) == count


def test_force_reembeds_without_duplicates(
    client: QdrantClient, settings: Settings, write_corpus: Callable[..., Path]
) -> None:
    manifest = write_corpus({"rbi-sample": [LONG]})
    run_ingest(manifest, client, FakeEmbedder(), settings)
    count = stored(client)
    embedder = FakeEmbedder()

    run_ingest(manifest, client, embedder, settings, force=True)

    assert embedder.embedded == count
    assert stored(client) == count


def test_shorter_new_version_removes_stale_chunks(
    client: QdrantClient, settings: Settings, write_corpus: Callable[..., Path]
) -> None:
    run_ingest(write_corpus({"rbi-sample": [LONG, LONG, LONG]}), client, FakeEmbedder(), settings)
    before = stored(client)

    summary = run_ingest(write_corpus({"rbi-sample": [LONG]}), client, FakeEmbedder(), settings)

    assert summary.docs_indexed == 1
    assert stored(client) == summary.chunks_total < before


def test_partially_indexed_document_is_repaired(
    client: QdrantClient, settings: Settings, write_corpus: Callable[..., Path]
) -> None:
    manifest = write_corpus({"rbi-sample": [LONG, LONG]})
    run_ingest(manifest, client, FakeEmbedder(), settings)
    count = stored(client)
    client.delete(COLLECTION, points_selector=[point_id("rbi-sample", 0)], wait=True)

    summary = run_ingest(manifest, client, FakeEmbedder(), settings)

    assert summary.docs_indexed == 1
    assert stored(client) == count


def test_scanned_document_is_skipped(
    client: QdrantClient, settings: Settings, write_corpus: Callable[..., Path]
) -> None:
    manifest = write_corpus({"rbi-scanned": ["", ""], "rbi-sample": [LONG]})

    summary = run_ingest(manifest, client, FakeEmbedder(), settings)

    assert (summary.docs_indexed, summary.docs_skipped, summary.docs_failed) == (1, 1, 0)


def test_one_bad_document_does_not_stop_the_rest(
    client: QdrantClient,
    settings: Settings,
    write_corpus: Callable[..., Path],
    tmp_path: Path,
) -> None:
    manifest = write_corpus({"rbi-broken": [LONG], "rbi-sample": [LONG]})
    broken = tmp_path / "raw" / "rbi-broken.pdf"
    broken.write_bytes(b"not a pdf")
    raw = yaml.safe_load(manifest.read_text("utf-8"))
    raw["documents"][0]["sha256"] = hashlib.sha256(b"not a pdf").hexdigest()
    manifest.write_text(yaml.safe_dump(raw), "utf-8")

    summary = run_ingest(manifest, client, FakeEmbedder(), settings)

    assert (summary.docs_indexed, summary.docs_failed) == (1, 1)


def test_invalid_manifest_stops_before_indexing(
    client: QdrantClient, settings: Settings, tmp_path: Path
) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("version: 1\ndocuments: []\n", "utf-8")

    with pytest.raises(ManifestError):
        run_ingest(manifest, client, FakeEmbedder(), settings)

    assert not client.collection_exists(COLLECTION)


def test_wrong_vector_size_is_refused(client: QdrantClient) -> None:
    ensure_collection(client, COLLECTION, size=128)

    with pytest.raises(IndexerError, match="vector size"):
        ensure_collection(client, COLLECTION, size=384)
