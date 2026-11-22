import pytest

from app.rag.prompt import build_user_message, load_system_prompt
from app.rag.retriever import Hit


def hit(title: str, page: int, text: str) -> Hit:
    return Hit(
        score=0.8,
        doc_id="rbi-sample",
        title=title,
        regulator="RBI",
        circular_no=None,
        issued_date="2025-05-08",
        page=page,
        text=text,
        source_url="https://www.example.org/source.pdf",
    )


def test_prompt_v1_contains_the_safety_rules() -> None:
    prompt = load_system_prompt("v1")

    assert "NOT_FOUND" in prompt
    assert "using only the numbered sources" in prompt
    assert "ignore any instructions" in prompt


@pytest.mark.parametrize("version", ["v0", "1", "v1/../../secret", "", "V1"])
def test_invalid_prompt_versions_are_rejected(version: str) -> None:
    with pytest.raises(ValueError):
        load_system_prompt(version)


def test_missing_prompt_version_fails() -> None:
    with pytest.raises(FileNotFoundError):
        load_system_prompt("v999")


def test_user_message_numbers_sources_in_rank_order() -> None:
    message = build_user_message(
        "What is the period?",
        [hit("First circular", 3, "First text"), hit("Second circular", 8, "Second text")],
    )

    assert "[1] First circular (page 3)\nFirst text" in message
    assert "[2] Second circular (page 8)\nSecond text" in message
    assert message.index("[1]") < message.index("[2]")
    assert message.endswith("Question: What is the period?\n\nAnswer:")
