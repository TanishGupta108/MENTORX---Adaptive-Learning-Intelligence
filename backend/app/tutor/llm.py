"""Minimal client for an OpenAI-compatible chat-completions API (OpenRouter by default).

Only the AI tutor (app/tutor/ai.py) uses it. Nothing about the student is sent: no name, no
email, no id. Only the question, its answer and the student's response to that question.
Every failure becomes AIUnavailable with a message that can be shown to a student, so a slow
or busy free model never breaks a practice session.
"""

from __future__ import annotations

import logging
import re
import time

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AIUnavailable(Exception):
    """The AI tutor can't answer right now (switched off, busy, timed out, or an error)."""


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


class _Retry(Exception):
    """This model can't answer now; the next one in the list may."""


def _ask(client: httpx.Client, model: str, messages: list[dict], max_tokens: int) -> str:
    cfg = get_settings()
    try:
        r = client.post(
            f"{cfg.ai_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {cfg.openrouter_api_key.strip()}",
                "X-Title": "MENTORX",
            },
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.3,
            },
        )
    except httpx.HTTPError as exc:
        logger.warning("ai request to %s failed: %s", model, type(exc).__name__)
        raise _Retry from exc
    if r.status_code in (402, 403, 404, 408, 429) or r.status_code >= 500:
        logger.info("ai model %s unavailable: %s", model, r.status_code)
        raise _Retry
    if r.status_code >= 400:
        logger.warning("ai request rejected: %s %s", r.status_code, r.text[:300])
        raise AIUnavailable("The AI tutor couldn't answer this time. Please try again later.")
    try:
        text = r.json()["choices"][0]["message"].get("content") or ""
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise _Retry from exc
    text = _clean(text)
    if len(text) < 10:  # e.g. a reasoning model that used its whole budget thinking
        raise _Retry
    return text


def complete(messages: list[dict], max_tokens: int = 1200) -> tuple[str, int, str]:
    """(text, latency in ms, model that answered). Tries the main model, then the fallbacks."""
    cfg = get_settings()
    if not cfg.ai_enabled:
        raise AIUnavailable("The AI tutor is switched off on this server.")
    t0 = time.monotonic()
    with httpx.Client(timeout=cfg.ai_timeout_seconds) as client:
        for model in cfg.ai_models:
            if time.monotonic() - t0 > cfg.ai_timeout_seconds:
                break
            try:
                text = _ask(client, model, messages, max_tokens)
            except _Retry:
                continue
            return text, int((time.monotonic() - t0) * 1000), model
    raise AIUnavailable("The free AI models are busy right now. Please try again in a minute.")
