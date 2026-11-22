"""Question answering: retrieve, refuse when unsupported, generate and cite."""

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

from app.config import Settings
from app.models.schemas import Citation, Filters, Latency
from app.rag.citations import apply_citations
from app.rag.generator import generate
from app.rag.prompt import build_user_message, load_system_prompt
from app.rag.retriever import retrieve, to_citations

REFUSAL_MESSAGE = (
    "I couldn't find this in the indexed RBI/SEBI circulars. "
    "Try rephrasing, or check the regulator's website."
)
NOT_FOUND_TOKEN = "NOT_FOUND"

RefusalReason = Literal["low_score", "llm_not_found", "no_citation"]


@dataclass(frozen=True)
class AskResult:
    answer: str
    citations: list[Citation]
    refused: bool
    model: str | None
    latency: Latency
    hits: int
    top_score: float | None
    refusal_reason: RefusalReason | None = None
    completion_tokens: int | None = None


def _ms(start: float, end: float) -> int:
    return round((end - start) * 1000)


def answer_question(
    question: str,
    top_k: int,
    filters: Filters | None,
    settings: Settings,
    embedder: Any,
    qdrant: Any,
) -> AskResult:
    started = perf_counter()
    vector = embedder.embed_query(question)
    embedded = perf_counter()
    hits = retrieve(qdrant, settings.qdrant_collection, vector, top_k, filters)
    retrieved = perf_counter()
    top_score = round(hits[0].score, 4) if hits else None

    def refuse(reason: RefusalReason, finished: float, tokens: int | None = None) -> AskResult:
        return AskResult(
            answer=REFUSAL_MESSAGE,
            citations=[],
            refused=True,
            model=None,
            latency=Latency(
                embed=_ms(started, embedded),
                retrieve=_ms(embedded, retrieved),
                generate=_ms(retrieved, finished),
                total=_ms(started, finished),
            ),
            hits=len(hits),
            top_score=top_score,
            refusal_reason=reason,
            completion_tokens=tokens,
        )

    # A weak match is refused here, before spending time on the LLM.
    if not hits or hits[0].score < settings.refusal_threshold:
        return refuse("low_score", retrieved)

    generation = generate(
        settings,
        load_system_prompt(settings.prompt_version),
        build_user_message(question, hits),
    )
    generated = perf_counter()
    if NOT_FOUND_TOKEN in generation.text.upper():
        return refuse("llm_not_found", generated, generation.completion_tokens)

    answer, cited = apply_citations(generation.text, range(1, len(hits) + 1))
    if not cited:
        return refuse("no_citation", generated, generation.completion_tokens)

    return AskResult(
        answer=answer,
        citations=[citation for citation in to_citations(hits) if citation.n in cited],
        refused=False,
        model=settings.llm_model,
        latency=Latency(
            embed=_ms(started, embedded),
            retrieve=_ms(embedded, retrieved),
            generate=_ms(retrieved, generated),
            total=_ms(started, generated),
        ),
        hits=len(hits),
        top_score=top_score,
        completion_tokens=generation.completion_tokens,
    )
