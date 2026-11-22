import hashlib
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.ingest.manifest import ManifestError, document_path, load_manifest


@pytest.fixture
def write_manifest(tmp_path: Path) -> Callable[..., Path]:
    def _write(*documents: dict[str, Any]) -> Path:
        path = tmp_path / "manifest.yaml"
        path.write_text(yaml.safe_dump({"version": 1, "documents": list(documents)}), "utf-8")
        return path

    return _write


@pytest.fixture
def entry(tmp_path: Path) -> dict[str, Any]:
    raw = tmp_path / "raw"
    raw.mkdir()
    pdf = raw / "circular.pdf"
    pdf.write_bytes(b"pdf bytes")
    return {
        "doc_id": "rbi-2025-sample",
        "file": "raw/circular.pdf",
        "title": "Sample Directions",
        "regulator": "RBI",
        "doc_type": "master_direction",
        "circular_no": "RBI/2025-26/01",
        "issued_date": date(2025, 5, 8),
        "source_url": "https://www.rbi.org.in/sample.pdf",
        "sha256": hashlib.sha256(b"pdf bytes").hexdigest(),
        "tags": ["sample"],
    }


def test_valid_manifest_loads(write_manifest: Callable[..., Path], entry: dict[str, Any]) -> None:
    path = write_manifest(entry)

    manifest = load_manifest(path)

    assert manifest.documents[0].doc_id == "rbi-2025-sample"
    assert document_path(path, manifest.documents[0]).name == "circular.pdf"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("doc_id", "Bad_ID"),
        ("doc_id", "abc"),
        ("regulator", "NSE"),
        ("doc_type", "press_release"),
        ("sha256", "abc123"),
        ("source_url", "not-a-url"),
        ("issued_date", date.today() + timedelta(days=1)),
    ],
)
def test_invalid_fields_are_rejected(
    write_manifest: Callable[..., Path], entry: dict[str, Any], field: str, value: Any
) -> None:
    path = write_manifest({**entry, field: value})

    with pytest.raises(ManifestError):
        load_manifest(path)


def test_duplicate_doc_ids_are_rejected(
    write_manifest: Callable[..., Path], entry: dict[str, Any]
) -> None:
    path = write_manifest(entry, dict(entry))

    with pytest.raises(ManifestError, match="duplicate"):
        load_manifest(path)


def test_missing_file_is_rejected(
    write_manifest: Callable[..., Path], entry: dict[str, Any]
) -> None:
    path = write_manifest({**entry, "file": "raw/missing.pdf"})

    with pytest.raises(ManifestError, match="not found"):
        load_manifest(path)


def test_checksum_mismatch_is_rejected(
    write_manifest: Callable[..., Path], entry: dict[str, Any], tmp_path: Path
) -> None:
    path = write_manifest(entry)
    (tmp_path / "raw" / "circular.pdf").write_bytes(b"changed")

    with pytest.raises(ManifestError, match="sha256"):
        load_manifest(path)


def test_path_outside_corpus_is_rejected(
    write_manifest: Callable[..., Path], entry: dict[str, Any]
) -> None:
    path = write_manifest({**entry, "file": "../outside.pdf"})

    with pytest.raises(ManifestError, match="outside"):
        load_manifest(path)


def test_malformed_yaml_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "manifest.yaml"
    path.write_text("version: [1", "utf-8")

    with pytest.raises(ManifestError):
        load_manifest(path)
