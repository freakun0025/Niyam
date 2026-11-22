"""Versioned system prompts and numbered source context."""

import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from app.rag.retriever import Hit

PROMPTS_DIR = Path(__file__).parent / "prompts"


@lru_cache
def load_system_prompt(version: str) -> str:
    """Load a prompt file such as prompts/v1.txt."""
    if not re.fullmatch(r"v[1-9][0-9]*", version):
        raise ValueError(f"invalid prompt version: {version}")
    return (PROMPTS_DIR / f"{version}.txt").read_text(encoding="utf-8").strip()


def build_user_message(question: str, hits: Sequence[Hit]) -> str:
    """Number sources to match the citations returned to the user."""
    sources = "\n\n".join(
        f"[{number}] {hit.title} (page {hit.page})\n{hit.text}"
        for number, hit in enumerate(hits, start=1)
    )
    return f"Sources:\n{sources}\n\nQuestion: {question}\n\nAnswer:"
