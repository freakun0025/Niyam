"""In-process text embeddings using fastembed."""

from collections.abc import Sequence
from pathlib import Path


class Embedder:
    """Wraps the embedding model, using separate modes for passages and queries."""

    def __init__(self, model_name: str, cache_dir: Path) -> None:
        # Imported here because loading the model runtime is slow and unit tests do not need it.
        from fastembed import TextEmbedding

        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name, cache_dir=str(cache_dir))

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.passage_embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()
