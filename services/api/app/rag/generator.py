"""Ollama chat client."""

import logging
from dataclasses import dataclass
from time import perf_counter
from typing import NoReturn

import httpx

from app.config import Settings
from app.logging import log_event

LLM_CONNECT_TIMEOUT_SECONDS = 5.0
LLM_KEEP_ALIVE = "30m"
LLM_SEED = 42


class LLMUnavailable(RuntimeError):
    """Ollama could not produce an answer."""


@dataclass(frozen=True)
class Generation:
    text: str
    completion_tokens: int | None


def _fail(error_type: str, started: float, cause: Exception) -> NoReturn:
    log_event(
        "llm.error",
        logging.ERROR,
        error_type=error_type,
        elapsed_ms=round((perf_counter() - started) * 1000),
    )
    raise LLMUnavailable(error_type) from cause


def generate(settings: Settings, system_prompt: str, user_message: str) -> Generation:
    """Request one deterministic, length-capped completion."""
    payload = {
        "model": settings.llm_model,
        "stream": False,
        "keep_alive": LLM_KEEP_ALIVE,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "options": {
            "num_predict": settings.llm_max_tokens,
            "temperature": settings.llm_temperature,
            "seed": LLM_SEED,
        },
    }
    started = perf_counter()
    try:
        response = httpx.post(
            f"{settings.ollama_url.rstrip('/')}/api/chat",
            json=payload,
            timeout=httpx.Timeout(settings.llm_timeout_s, connect=LLM_CONNECT_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
        data = response.json()
        text = data["message"]["content"].strip()
    except httpx.TimeoutException as exc:
        _fail("timeout", started, exc)
    except httpx.HTTPStatusError as exc:
        _fail("http", started, exc)
    except httpx.TransportError as exc:
        _fail("connect", started, exc)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        _fail("http", started, exc)
    return Generation(text=text, completion_tokens=data.get("eval_count"))
