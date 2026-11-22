import pytest

from app.ingest.chunker import chunk_pages
from app.ingest.pdf_parser import PageText

SENTENCE = "The regulated entity shall provide a cooling-off period to every borrower. "


def test_short_page_stays_one_chunk() -> None:
    text = SENTENCE.strip()

    chunks = chunk_pages([PageText(3, text)], min_chars=10)

    assert len(chunks) == 1
    assert (chunks[0].chunk_index, chunks[0].page, chunks[0].text) == (0, 3, text)


def test_long_page_respects_chunk_size() -> None:
    chunks = chunk_pages([PageText(1, SENTENCE * 60)], size=800, overlap=120)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 800 for chunk in chunks)


def test_chunks_prefer_sentence_boundaries() -> None:
    chunks = chunk_pages([PageText(1, SENTENCE * 60)], size=800, overlap=120)

    assert all(chunk.text.endswith(".") for chunk in chunks)


def test_neighbouring_chunks_overlap() -> None:
    words = " ".join(f"word{number}" for number in range(600))

    chunks = chunk_pages([PageText(1, words)], size=400, overlap=80)

    for current, following in zip(chunks, chunks[1:], strict=False):
        assert following.text.split()[0] in current.text.split()


def test_all_words_are_covered() -> None:
    words = [f"word{number}" for number in range(600)]

    chunks = chunk_pages([PageText(1, " ".join(words))], size=400, overlap=80)

    covered = {word for chunk in chunks for word in chunk.text.split()}
    assert covered == set(words)


def test_chunks_never_cross_pages() -> None:
    pages = [PageText(1, "alpha " * 200), PageText(2, "omega " * 200)]

    chunks = chunk_pages(pages)

    assert {chunk.page for chunk in chunks} == {1, 2}
    assert all("omega" not in chunk.text for chunk in chunks if chunk.page == 1)
    assert all("alpha" not in chunk.text for chunk in chunks if chunk.page == 2)


def test_chunk_indexes_are_continuous_across_pages() -> None:
    pages = [PageText(1, SENTENCE * 30), PageText(2, "tiny"), PageText(3, SENTENCE * 30)]

    chunks = chunk_pages(pages)

    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_tiny_chunks_are_dropped() -> None:
    assert chunk_pages([PageText(1, "Page 4 of 40")]) == []


def test_table_of_contents_is_dropped() -> None:
    index = " ".join(f"Chapter {number} ........................ {number}" for number in range(9))

    assert chunk_pages([PageText(1, index)]) == []


def test_ordinary_ellipsis_is_kept() -> None:
    text = f"{SENTENCE} The list continues .... and ends here. {SENTENCE}"

    assert len(chunk_pages([PageText(1, text)])) == 1


def test_chunking_is_deterministic() -> None:
    pages = [PageText(1, SENTENCE * 40), PageText(2, SENTENCE * 25)]

    assert chunk_pages(pages) == chunk_pages(pages)


def test_text_without_spaces_still_terminates() -> None:
    chunks = chunk_pages([PageText(1, "x" * 2000)], size=500, overlap=100)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 500 for chunk in chunks)


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (100, 50), (100, -1), (100, 80)])
def test_invalid_settings_are_rejected(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_pages([PageText(1, "text")], size=size, overlap=overlap)
