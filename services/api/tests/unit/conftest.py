from collections.abc import Callable
from pathlib import Path

import pytest


def build_pdf(page_texts: list[str]) -> bytes:
    """Build a minimal valid PDF with one line of Helvetica text per page."""
    kids = " ".join(f"{4 + index * 2} 0 R" for index in range(len(page_texts)))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_texts)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, text in enumerate(page_texts):
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 8 Tf 20 750 Td ({escaped}) Tj ET".encode("latin-1")
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + index * 2} 0 R >>"
            ).encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))

    output = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += b"%d 0 obj\n%s\nendobj\n" % (number, body)

    xref_at = len(output)
    output += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        output += b"%010d 00000 n \n" % offset
    output += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    output += b"startxref\n%d\n%%%%EOF\n" % xref_at
    return bytes(output)


@pytest.fixture
def make_pdf(tmp_path: Path) -> Callable[..., Path]:
    def _make_pdf(page_texts: list[str], name: str = "document.pdf") -> Path:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(build_pdf(page_texts))
        return path

    return _make_pdf
