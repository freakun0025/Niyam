"""Per-page PDF text extraction with scanned-document detection."""

import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

MIN_CHARS_PER_PAGE = 200


class PdfParseError(ValueError):
    """A PDF could not be opened or read."""


@dataclass(frozen=True)
class PageText:
    number: int  # 1-indexed, matching the page shown in citations.
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    pages: tuple[PageText, ...]

    @property
    def chars_per_page(self) -> float:
        if not self.pages:
            return 0.0
        return sum(len(page.text) for page in self.pages) / len(self.pages)

    @property
    def is_scanned(self) -> bool:
        return self.chars_per_page < MIN_CHARS_PER_PAGE


def clean_text(text: str) -> str:
    """Remove NUL bytes, rejoin words hyphenated across lines and collapse whitespace."""
    text = text.replace("\x00", "")
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_pdf(path: Path) -> ParsedDocument:
    """Extract cleaned text from every page of a PDF."""
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise PdfParseError(f"{path.name}: PDF is password protected")
        pages = tuple(
            PageText(number=number, text=clean_text(page.extract_text() or ""))
            for number, page in enumerate(reader.pages, start=1)
        )
    except PdfParseError:
        raise
    except (PyPdfError, OSError, ValueError, KeyError, TypeError) as exc:
        raise PdfParseError(f"{path.name}: could not read PDF: {exc}") from exc
    return ParsedDocument(pages=pages)
