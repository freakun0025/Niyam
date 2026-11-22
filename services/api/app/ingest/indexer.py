"""Idempotent storage of document chunks in Qdrant (schema: DATA_MODEL section 2)."""

from collections.abc import Sequence
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.ingest.chunker import Chunk
from app.ingest.manifest import ManifestEntry

VECTOR_SIZE = 384
UPSERT_BATCH_SIZE = 64
PAYLOAD_INDEXES = (
    ("regulator", models.PayloadSchemaType.KEYWORD),
    ("doc_id", models.PayloadSchemaType.KEYWORD),
    ("issued_year", models.PayloadSchemaType.INTEGER),
)


class IndexerError(RuntimeError):
    """The vector collection cannot be used safely."""


def point_id(doc_id: str, chunk_index: int) -> str:
    """Return a stable ID, so indexing the same chunk again overwrites it."""
    return str(uuid5(NAMESPACE_URL, f"{doc_id}:{chunk_index}"))


def ensure_collection(client: QdrantClient, collection: str, size: int = VECTOR_SIZE) -> None:
    """Create the collection if needed and refuse one built for a different vector size."""
    if client.collection_exists(collection):
        configured = client.get_collection(collection).config.params.vectors.size
        if configured != size:
            raise IndexerError(f"{collection} has vector size {configured}, expected {size}")
    else:
        client.create_collection(
            collection,
            vectors_config=models.VectorParams(size=size, distance=models.Distance.COSINE),
        )
    for field, schema in PAYLOAD_INDEXES:
        client.create_payload_index(collection, field, schema)


def _doc_filter(doc_id: str, *conditions: models.FieldCondition) -> models.Filter:
    doc_condition = models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))
    return models.Filter(must=[doc_condition, *conditions])


def _match(key: str, value: str) -> models.FieldCondition:
    return models.FieldCondition(key=key, match=models.MatchValue(value=value))


def is_current(
    client: QdrantClient,
    collection: str,
    entry: ManifestEntry,
    chunk_count: int,
    embed_model: str,
) -> bool:
    """Return True only if every chunk is stored for this file version and embedding model."""
    total = client.count(collection, count_filter=_doc_filter(entry.doc_id), exact=True).count
    matching = client.count(
        collection,
        count_filter=_doc_filter(
            entry.doc_id,
            _match("doc_sha256", entry.sha256),
            _match("embed_model", embed_model),
        ),
        exact=True,
    ).count
    return total == matching == chunk_count


def build_payload(
    entry: ManifestEntry, chunk: Chunk, embed_model: str, ingest_run_id: str
) -> dict[str, Any]:
    return {
        "doc_id": entry.doc_id,
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
        "page_start": chunk.page,
        "page_end": chunk.page,
        "title": entry.title,
        "regulator": entry.regulator,
        "doc_type": entry.doc_type,
        "circular_no": entry.circular_no,
        "issued_date": entry.issued_date.isoformat(),
        "issued_year": entry.issued_date.year,
        "source_url": str(entry.source_url),
        "doc_sha256": entry.sha256,
        "embed_model": embed_model,
        "ingest_run_id": ingest_run_id,
    }


def store_document(
    client: QdrantClient,
    collection: str,
    entry: ManifestEntry,
    chunks: Sequence[Chunk],
    vectors: Sequence[Sequence[float]],
    embed_model: str,
    ingest_run_id: str,
) -> None:
    """Upsert a document's chunks, then remove chunks left over from a longer old version."""
    if len(chunks) != len(vectors):
        raise IndexerError(f"{entry.doc_id}: got {len(vectors)} vectors for {len(chunks)} chunks")

    points = [
        models.PointStruct(
            id=point_id(entry.doc_id, chunk.chunk_index),
            vector=list(vector),
            payload=build_payload(entry, chunk, embed_model, ingest_run_id),
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    for start in range(0, len(points), UPSERT_BATCH_SIZE):
        client.upsert(collection, points=points[start : start + UPSERT_BATCH_SIZE], wait=True)

    stale = models.FieldCondition(key="chunk_index", range=models.Range(gte=len(chunks)))
    client.delete(
        collection,
        points_selector=models.FilterSelector(filter=_doc_filter(entry.doc_id, stale)),
        wait=True,
    )
