import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app.config import Settings
from app.rag.embedder import PASSAGE_BATCH_SIZE, Embedder


class FakeTextEmbedding:
    created: dict[str, Any] = {}
    batch_size: int | None = None

    def __init__(self, **kwargs: Any) -> None:
        FakeTextEmbedding.created = kwargs

    def passage_embed(self, texts: list[str], batch_size: int) -> Iterator[np.ndarray]:
        FakeTextEmbedding.batch_size = batch_size
        return (np.array([1.0, float(len(text))]) for text in texts)

    def query_embed(self, text: str) -> Iterator[np.ndarray]:
        return iter([np.array([2.0, float(len(text))])])


@pytest.fixture(autouse=True)
def fake_fastembed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=FakeTextEmbedding))


@pytest.mark.parametrize("offline", [True, False])
def test_offline_mode_controls_model_loading(offline: bool) -> None:
    Embedder("model-name", Path("/models"), offline=offline)

    assert FakeTextEmbedding.created == {
        "model_name": "model-name",
        "cache_dir": str(Path("/models")),
        "local_files_only": offline,
        "threads": 1,
    }


def test_passages_and_queries_use_their_own_modes() -> None:
    embedder = Embedder("model-name", Path("/models"))

    assert embedder.embed_passages(["ab", "abcd"]) == [[1.0, 2.0], [1.0, 4.0]]
    assert embedder.embed_query("abc") == [2.0, 3.0]


def test_passages_use_a_memory_safe_batch_size() -> None:
    Embedder("model-name", Path("/models")).embed_passages(["text"])

    assert FakeTextEmbedding.batch_size == PASSAGE_BATCH_SIZE <= 16


def test_offline_setting_is_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIYAM_EMBED_OFFLINE", "true")

    assert Settings().embed_offline is True
