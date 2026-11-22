"""Keep only citation markers that point to a source actually provided."""

import re
from collections.abc import Collection

_CITATION_GROUP = re.compile(r"\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]")


def apply_citations(answer: str, valid_numbers: Collection[int]) -> tuple[str, list[int]]:
    """Normalize markers to [n], remove invalid ones and return the cited numbers."""
    cited: set[int] = set()

    def replace(match: re.Match[str]) -> str:
        kept: list[int] = []
        for raw in match.group(1).split(","):
            number = int(raw)
            if number in valid_numbers and number not in kept:
                kept.append(number)
        cited.update(kept)
        return "".join(f"[{number}]" for number in kept)

    text = _CITATION_GROUP.sub(replace, answer)
    text = re.sub(r"[ \t]+([.,;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    return text, sorted(cited)
