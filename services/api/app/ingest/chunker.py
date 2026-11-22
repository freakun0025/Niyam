"""Page-bounded text chunking, so every chunk maps to one citable page."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from app.ingest.pdf_parser import PageText

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MIN_CHUNK_CHARS = 80


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    page: int
    text: str


def _split_text(text: str, size: int, overlap: int) -> Iterator[str]:
    start = 0
    length = len(text)
    while start < length:
        end = min(start + size, length)
        if end < length:
            floor = start + size // 2
            sentence_end = text.rfind(". ", floor, end)
            word_end = text.rfind(" ", floor, end)
            if sentence_end != -1:
                end = sentence_end + 1
            elif word_end != -1:
                end = word_end

        yield text[start:end].strip()
        if end >= length:
            return

        next_start = max(end - overlap, start + 1)
        boundary = text.find(" ", next_start, end)
        start = boundary + 1 if boundary != -1 else next_start


def chunk_pages(
    pages: Iterable[PageText],
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    min_chars: int = MIN_CHUNK_CHARS,
) -> list[Chunk]:
    """Split each page separately and number the kept chunks across the document."""
    if size <= 0 or overlap < 0 or overlap >= size // 2:
        raise ValueError("size must be positive and overlap must be under half of size")

    chunks: list[Chunk] = []
    for page in pages:
        for text in _split_text(page.text, size, overlap):
            if len(text) >= min_chars:
                chunks.append(Chunk(chunk_index=len(chunks), page=page.number, text=text))
    return chunks
