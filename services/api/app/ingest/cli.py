"""Corpus ingest command: python -m app.ingest.cli --manifest <path>."""

import argparse
import logging
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from qdrant_client import QdrantClient

from app.config import Settings, get_settings
from app.deps import build_qdrant_client
from app.ingest.chunker import chunk_pages
from app.ingest.indexer import ensure_collection, is_current, store_document
from app.ingest.manifest import ManifestEntry, ManifestError, document_path, load_manifest
from app.ingest.pdf_parser import parse_pdf
from app.logging import configure_logging, log_event
from app.rag.embedder import Embedder

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BAD_MANIFEST = 2


class PassageEmbedder(Protocol):
    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass
class IngestSummary:
    ingest_run_id: str
    docs_indexed: int = 0
    docs_skipped: int = 0
    docs_failed: int = 0
    chunks_total: int = 0


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _skip(summary: IngestSummary, entry: ManifestEntry, chunks: int, reason: str, started: float):
    summary.docs_skipped += 1
    log_event(
        "ingest.doc_skipped",
        doc_id=entry.doc_id,
        chunks=chunks,
        reason=reason,
        elapsed_ms=_elapsed_ms(started),
    )


def _ingest_document(
    manifest_path: Path,
    entry: ManifestEntry,
    client: QdrantClient,
    embedder: PassageEmbedder,
    settings: Settings,
    summary: IngestSummary,
    force: bool,
) -> None:
    started = time.perf_counter()
    parsed = parse_pdf(document_path(manifest_path, entry))
    chunks = chunk_pages(parsed.pages)
    if parsed.is_scanned or not chunks:
        _skip(summary, entry, 0, "scanned", started)
        return

    summary.chunks_total += len(chunks)
    collection = settings.qdrant_collection
    if not force and is_current(client, collection, entry, len(chunks), settings.embed_model):
        _skip(summary, entry, len(chunks), "unchanged", started)
        return

    vectors = embedder.embed_passages([chunk.text for chunk in chunks])
    store_document(
        client, collection, entry, chunks, vectors, settings.embed_model, summary.ingest_run_id
    )
    summary.docs_indexed += 1
    log_event(
        "ingest.doc_indexed",
        doc_id=entry.doc_id,
        chunks=len(chunks),
        elapsed_ms=_elapsed_ms(started),
    )


def run_ingest(
    manifest_path: Path,
    client: QdrantClient,
    embedder: PassageEmbedder,
    settings: Settings,
    force: bool = False,
) -> IngestSummary:
    """Index every changed document. One bad document does not stop the others."""
    started = time.perf_counter()
    manifest = load_manifest(manifest_path)
    ensure_collection(client, settings.qdrant_collection)
    summary = IngestSummary(ingest_run_id=f"{settings.app_version[:8]}-{int(time.time())}")

    for entry in manifest.documents:
        document_started = time.perf_counter()
        try:
            _ingest_document(manifest_path, entry, client, embedder, settings, summary, force)
        except Exception as exc:
            summary.docs_failed += 1
            log_event(
                "ingest.doc_skipped",
                logging.ERROR,
                doc_id=entry.doc_id,
                chunks=0,
                reason="error",
                error_type=type(exc).__name__,
                error_message=str(exc),
                elapsed_ms=_elapsed_ms(document_started),
            )

    log_event(
        "ingest.completed",
        ingest_run_id=summary.ingest_run_id,
        docs_indexed=summary.docs_indexed,
        docs_skipped=summary.docs_skipped,
        docs_failed=summary.docs_failed,
        chunks_total=summary.chunks_total,
        elapsed_ms=_elapsed_ms(started),
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings)

    parser = argparse.ArgumentParser(description="Index the RBI/SEBI corpus into Qdrant.")
    parser.add_argument("--manifest", type=Path, default=settings.corpus_manifest)
    parser.add_argument("--force", action="store_true", help="re-embed unchanged documents")
    args = parser.parse_args(argv)

    try:
        client = build_qdrant_client(settings)
        embedder = Embedder(settings.embed_model, settings.embed_cache)
        summary = run_ingest(args.manifest, client, embedder, settings, force=args.force)
    except ManifestError as exc:
        log_event(
            "ingest.failed", logging.ERROR, error_type="ManifestError", error_message=str(exc)
        )
        return EXIT_BAD_MANIFEST
    except Exception as exc:
        log_event(
            "ingest.failed",
            logging.ERROR,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return EXIT_FAILED
    return EXIT_FAILED if summary.docs_failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
