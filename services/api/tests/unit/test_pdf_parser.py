from collections.abc import Callable
from pathlib import Path

import pytest

from app.ingest.pdf_parser import PageText, ParsedDocument, PdfParseError, clean_text, parse_pdf

LONG_TEXT = "Regulated entities shall disclose the key fact statement to borrowers. " * 5


def test_extracts_text_per_page(make_pdf: Callable[..., Path]) -> None:
    path = make_pdf([f"First page. {LONG_TEXT}", f"Second page. {LONG_TEXT}"])

    document = parse_pdf(path)

    assert [page.number for page in document.pages] == [1, 2]
    assert document.pages[0].text.startswith("First page.")
    assert document.pages[1].text.startswith("Second page.")
    assert document.is_scanned is False


def test_pages_without_text_are_detected_as_scanned(make_pdf: Callable[..., Path]) -> None:
    path = make_pdf(["", "x"])

    assert parse_pdf(path).is_scanned is True


def test_empty_document_counts_as_scanned() -> None:
    assert ParsedDocument(pages=()).is_scanned is True


def test_scanned_threshold_uses_average_characters() -> None:
    document = ParsedDocument(pages=(PageText(1, "a" * 400), PageText(2, "")))

    assert document.chars_per_page == 200
    assert document.is_scanned is False


def test_invalid_pdf_raises_parse_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"this is not a pdf")

    with pytest.raises(PdfParseError):
        parse_pdf(path)


def test_missing_pdf_raises_parse_error(tmp_path: Path) -> None:
    with pytest.raises(PdfParseError):
        parse_pdf(tmp_path / "missing.pdf")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("lending   rules\n\nfor banks", "lending rules for banks"),
        ("regu-\nlated entity", "regulated entity"),
        ("cooling-off period", "cooling-off period"),
        ("nul\x00 byte", "nul byte"),
        ("  padded  ", "padded"),
    ],
)
def test_clean_text(raw: str, expected: str) -> None:
    assert clean_text(raw) == expected
