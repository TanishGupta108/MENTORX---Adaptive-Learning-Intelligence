"""Choosing the next question (FR-QUIZ-02, FR-QUIZ-10). Pure functions: no database."""

from __future__ import annotations

import random
from collections.abc import Sequence


def select_index(
    predictions: Sequence[float],
    group: str | None,
    target: float,
    top_k: int,
    rng: random.Random,
) -> int:
    """Index of the candidate to serve.

    adaptive (default): random among the top_k candidates whose predicted P(correct) is
        closest to `target`. A little randomness avoids always serving the same question
        and gives the retraining data some variety (design decision D-9).
    control (pilot): uniformly random, ignoring predictions. Everything else is identical,
        so the pilot isolates the effect of ML-based selection.
    """
    if not predictions:
        raise ValueError("no candidates")
    if group == "control":
        return rng.randrange(len(predictions))
    ranked = sorted(range(len(predictions)), key=lambda i: (abs(predictions[i] - target), i))
    return rng.choice(ranked[: max(1, top_k)])
