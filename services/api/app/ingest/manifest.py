"""Corpus manifest model and validation (schema: DATA_MODEL section 1)."""

import hashlib
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator, model_validator


class ManifestError(ValueError):
    """The corpus manifest or one of its files is invalid."""


class ManifestEntry(BaseModel):
    doc_id: str = Field(pattern=r"^[a-z0-9-]{5,80}$")
    file: str = Field(min_length=1)
    title: str = Field(min_length=1)
    regulator: Literal["RBI", "SEBI"]
    doc_type: Literal["master_direction", "master_circular", "circular", "notification"]
    circular_no: str | None = None
    issued_date: date
    source_url: HttpUrl
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tags: list[str] = Field(default_factory=list)

    @field_validator("issued_date")
    @classmethod
    def issued_date_not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("issued_date cannot be in the future")
        return value


class Manifest(BaseModel):
    version: Literal[1]
    documents: list[ManifestEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def doc_ids_are_unique(self) -> "Manifest":
        doc_ids = [entry.doc_id for entry in self.documents]
        duplicates = sorted({doc_id for doc_id in doc_ids if doc_ids.count(doc_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate doc_id values: {', '.join(duplicates)}")
        return self


def document_path(manifest_path: Path, entry: ManifestEntry) -> Path:
    """Return a document's path, refusing locations outside the manifest directory."""
    base = manifest_path.resolve().parent
    path = (base / entry.file).resolve()
    if not path.is_relative_to(base):
        raise ManifestError(f"{entry.doc_id}: file is outside the corpus directory")
    return path


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def load_manifest(manifest_path: Path) -> Manifest:
    """Load a manifest and verify that every listed file exists and matches its checksum."""
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest = Manifest.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ManifestError(f"invalid manifest {manifest_path}: {exc}") from exc

    for entry in manifest.documents:
        path = document_path(manifest_path, entry)
        if not path.is_file():
            raise ManifestError(f"{entry.doc_id}: file not found: {entry.file}")
        if _sha256(path) != entry.sha256:
            raise ManifestError(f"{entry.doc_id}: sha256 does not match {entry.file}")
    return manifest
