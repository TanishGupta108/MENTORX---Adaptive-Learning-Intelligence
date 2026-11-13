"""Minimal client for an OpenAI-compatible chat-completions API (OpenRouter by default).

Only the AI tutor (app/tutor/ai.py) uses it. Nothing about the student is sent: no name, no
email, no id. Only the question, its answer and the student's response to that question.

Reliability rules (free models are often busy or slow):
- Models are tried in order (config AI_MODEL, then AI_FALLBACK_MODELS); the model that last
  answered is tried first for 5 minutes.
- One request never takes longer than AI_TOTAL_SECONDS (default 50 s, below the 120 s proxy
  limit): each attempt waits at most 25 s for data, the body is read in chunks and dropped as
  soon as the total deadline passes (a provider sending keep-alive bytes can't stretch it), and
  no new model is started with < 5 s left.
- Reasoning is asked to be short and hidden ("effort": "low"); a model that rejects the
  reasoning field (400) is retried once without it.
- 401/403 mean the API key itself is rejected: that is logged as an ERROR (never the key),
  remembered for 10 minutes (`key_ok() is False`, so the AI buttons hide), and no other model
  is tried. Any other failure moves on to the next model.
Every failure becomes AIUnavailable (or AIKeyRejected) with a message safe to show a student.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

KEY_REJECT_SECONDS = 600
LAST_GOOD_SECONDS = 300
MIN_START_SECONDS = 5
MAX_READ_SECONDS = 25

# Test seams: a fake clock and an httpx transport (tests never reach the real API).
_clock = time.monotonic
_transport: httpx.BaseTransport | None = None

_lock = threading.Lock()
_state: dict = {"key_rejected_at": None, "key_ok": None, "last_good": None}


class AIUnavailable(Exception):
    """The AI tutor can't answer right now (switched off, busy, timed out, or an error)."""


class AIKeyRejected(AIUnavailable):
    """OpenRouter rejected the API key (401/403). Not retryable until the key is fixed."""


class _Retry(Exception):
    """This model can't answer now; the next one in the list may."""


class _NoReasoning(Exception):
    """The model rejected the `reasoning` field; ask it again without."""


def reset_state() -> None:
    with _lock:
        _state.update(key_rejected_at=None, key_ok=None, last_good=None)


def key_ok() -> bool | None:
    """False after OpenRouter rejected the key (for 10 minutes), True after a success,
    None when nothing is known yet."""
    with _lock:
        t = _state["key_rejected_at"]
        if t is not None:
            if _clock() - t < KEY_REJECT_SECONDS:
                return False
            _state["key_rejected_at"] = None
            _state["key_ok"] = None  # unknown again: the next request will tell
        return _state["key_ok"]


def _mark_rejected(status: int) -> None:
    logger.error("OpenRouter rejected the API key (status %s)", status)
    with _lock:
        _state["key_rejected_at"] = _clock()
        _state["key_ok"] = False


def _mark_good(model: str) -> None:
    with _lock:
        _state["key_rejected_at"] = None
        _state["key_ok"] = True
        _state["last_good"] = (model, _clock())


def _ordered_models() -> list[str]:
    models = get_settings().ai_models
    with _lock:
        last = _state["last_good"]
    if last and _clock() - last[1] < LAST_GOOD_SECONDS and last[0] in models:
        return [last[0], *[m for m in models if m != last[0]]]
    return models


def _clean(text: str) -> str:
    """Strip reasoning tags and LaTeX the notes renderer can't show."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I)
    text = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", text)
    text = re.sub(r"\\sqrt\{([^{}]*)\}", r"sqrt(\1)", text)
    for a, b in (
        (r"\times", "×"),
        (r"\cdot", "·"),
        (r"\div", "÷"),
        (r"\pi", "π"),
        (r"\le", "≤"),
        (r"\ge", "≥"),
        (r"\neq", "≠"),
        (r"\left", ""),
        (r"\right", ""),
        (r"\(", ""),
        (r"\)", ""),
        (r"\[", ""),
        (r"\]", ""),
        ("$$", ""),
    ):
        text = text.replace(a, b)
    text = re.sub(r"(?<!\\)\$", "", text)
    text = re.sub(r"\^\{([^{}]*)\}", r"^\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _ask(
    client: httpx.Client,
    model: str,
    messages: list[dict],
    max_tokens: int,
    timeout: httpx.Timeout,
    reasoning: bool,
    min_chars: int,
    deadline: float,
) -> str:
    cfg = get_settings()
    body: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    if reasoning:
        body["reasoning"] = {"effort": "low", "exclude": True}
    try:
        with client.stream(
            "POST",
            f"{cfg.ai_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.openrouter_api_key}", "X-Title": "MENTORX"},
            json=body,
            timeout=timeout,
        ) as r:
            status, chunks = r.status_code, []
            for chunk in r.iter_bytes():  # a hard cap: stop reading once the budget is spent
                chunks.append(chunk)
                if _clock() > deadline:
                    logger.info("ai model %s ran past the time budget", model)
                    raise _Retry
    except httpx.HTTPError as exc:
        logger.warning("ai request to %s failed: %s", model, type(exc).__name__)
        raise _Retry from exc
    raw = b"".join(chunks).decode("utf-8", errors="replace")
    if status in (401, 403):
        _mark_rejected(status)
        raise AIKeyRejected("The AI tutor isn't available right now.")
    if status == 400 and reasoning and "reasoning" in raw.lower():
        raise _NoReasoning
    if status in (402, 404, 408, 429) or status >= 500:
        logger.info("ai model %s unavailable: %s", model, status)
        raise _Retry
    if status >= 400:
        logger.warning("ai model %s refused the request: %s %s", model, status, raw[:200])
        raise _Retry
    try:
        text = json.loads(raw)["choices"][0]["message"].get("content") or ""
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise _Retry from exc
    text = _clean(text)
    if len(text) < min_chars:  # e.g. a reasoning model that used its whole budget thinking
        raise _Retry
    return text


def complete(
    messages: list[dict],
    max_tokens: int = 1200,
    *,
    min_chars: int = 10,
    ignore_key_flag: bool = False,
) -> tuple[str, int, str]:
    """(text, latency in ms, model that answered). Tries the models in order within the
    total time budget."""
    cfg = get_settings()
    if not cfg.ai_enabled:
        raise AIUnavailable("The AI tutor is switched off on this server.")
    if not ignore_key_flag and key_ok() is False:
        raise AIKeyRejected("The AI tutor isn't available right now.")
    t0 = _clock()
    total = cfg.ai_total_seconds
    with httpx.Client(transport=_transport) as client:
        for model in _ordered_models():
            reasoning = True
            while True:
                remaining = total - (_clock() - t0)
                if remaining < MIN_START_SECONDS:
                    break
                read = max(1.0, min(MAX_READ_SECONDS, remaining - 5))
                timeout = httpx.Timeout(connect=5, read=read, write=5, pool=5)
                try:
                    text = _ask(
                        client,
                        model,
                        messages,
                        max_tokens,
                        timeout,
                        reasoning,
                        min_chars,
                        t0 + total,  # the hard deadline for the whole request
                    )
                except _NoReasoning:
                    reasoning = False  # once, without the reasoning field
                    continue
                except _Retry:
                    break
                _mark_good(model)
                return text, int((_clock() - t0) * 1000), model
            if total - (_clock() - t0) < MIN_START_SECONDS:
                break
    raise AIUnavailable("The free AI models are busy right now. Please try again in a minute.")


def check_connection() -> dict:
    """Admin check: a tiny prompt through the real chain. Never includes the key."""
    t0 = _clock()
    try:
        text, latency, model = complete(
            [{"role": "user", "content": "Reply with OK"}],
            max_tokens=200,
            min_chars=1,
            ignore_key_flag=True,
        )
    except AIKeyRejected as exc:
        return {
            "ok": False,
            "model": None,
            "latency_ms": int((_clock() - t0) * 1000),
            "error_code": "ai_key_rejected",
            "message": f"OpenRouter rejected the API key. {exc}",
        }
    except AIUnavailable as exc:
        disabled = not get_settings().ai_enabled
        return {
            "ok": False,
            "model": None,
            "latency_ms": None if disabled else int((_clock() - t0) * 1000),
            "error_code": "ai_disabled" if disabled else "ai_unavailable",
            "message": str(exc),
        }
    return {
        "ok": True,
        "model": model,
        "latency_ms": latency,
        "error_code": None,
        "message": f"The AI answered: {text[:60]}",
    }
