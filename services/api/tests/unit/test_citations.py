import pytest

from app.rag.citations import apply_citations


@pytest.mark.parametrize(
    ("answer", "expected_text", "expected_cited"),
    [
        ("The period is one day [1].", "The period is one day [1].", [1]),
        ("Rule A [2] and rule B [1].", "Rule A [2] and rule B [1].", [1, 2]),
        ("Both apply [1, 2].", "Both apply [1][2].", [1, 2]),
        ("Spaced [ 3 ].", "Spaced [3].", [3]),
        ("Repeated [1] and [1].", "Repeated [1] and [1].", [1]),
        ("Duplicate group [2, 2].", "Duplicate group [2].", [2]),
        ("Invented source [9].", "Invented source.", []),
        ("Mixed group [1, 9].", "Mixed group [1].", [1]),
        ("Zero is invalid [0].", "Zero is invalid.", []),
        ("No citations here.", "No citations here.", []),
        ("Text [note] stays.", "Text [note] stays.", []),
    ],
)
def test_apply_citations(answer: str, expected_text: str, expected_cited: list[int]) -> None:
    assert apply_citations(answer, range(1, 5)) == (expected_text, expected_cited)
