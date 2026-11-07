"""Fast, incremental feature computation for serving (design decision D-3).

Training uses `features.history_features`, a vectorised pass over a whole table.
At serving time we need features for ~50 candidate questions for ONE student, many
times a minute, so we summarise the student's history once (`StudentState`) and then
compute each candidate's feature row in O(1).

`tests/test_serve.py` proves that for every row of random histories, the features
computed here equal the training features exactly. That equivalence is what keeps
training and serving from drifting apart.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from mentorx_ml.features import LAST_K_CONCEPT, LAST_K_OVERALL


def _smoothed(k: float, n: float) -> float:
    return (k + 1.0) / (n + 2.0)


@dataclass
class _ConceptStats:
    n: int = 0
    k: int = 0
    last: deque = field(default_factory=lambda: deque(maxlen=LAST_K_CONCEPT))
    last_seq: int | None = None
    last_time: datetime | None = None


@dataclass
class _ItemStats:
    n: int = 0
    k: int = 0


@dataclass
class StudentState:
    """Everything the history features need, updated one attempt at a time."""

    n: int = 0
    k: int = 0
    last10: deque = field(default_factory=lambda: deque(maxlen=LAST_K_OVERALL))
    last_time: datetime | None = None
    concepts: dict[str, _ConceptStats] = field(default_factory=dict)
    items: dict[str, _ItemStats] = field(default_factory=dict)

    @classmethod
    def from_history(cls, history: list[tuple[str, str, int, datetime | None]]) -> StudentState:
        """history: (concept_id, item_id, correct, timestamp) in time order."""
        state = cls()
        for concept, item, correct, ts in history:
            state.update(concept, item, correct, ts)
        return state

    def update(self, concept: str, item: str, correct: int, ts: datetime | None) -> None:
        c = self.concepts.setdefault(concept, _ConceptStats())
        c.n += 1
        c.k += correct
        c.last.append(correct)
        c.last_seq = self.n
        c.last_time = ts
        i = self.items.setdefault(item, _ItemStats())
        i.n += 1
        i.k += correct
        self.n += 1
        self.k += correct
        self.last10.append(correct)
        self.last_time = ts

    def history_row(
        self, concept: str, item: str, now: datetime | None, use_time: bool
    ) -> dict[str, float]:
        """History features for a candidate (concept, item) answered next, at time `now`."""
        c = self.concepts.get(concept)
        i = self.items.get(item)
        n_c = c.n if c else 0
        last_c = list(c.last) if c else []
        prev = last_c[-1] if last_c else None
        gap = (self.n - c.last_seq - 1) if c else 0
        row = {
            "log_prior_concept": float(np.log1p(n_c)),
            "acc_concept": _smoothed(c.k if c else 0, n_c),
            "acc_concept_last3": _smoothed(sum(last_c), len(last_c)),
            "prev_concept": 0.0 if prev is None else (1.0 if prev == 1 else -1.0),
            "is_first_concept": 1.0 if n_c == 0 else 0.0,
            "log_gap_concept": float(np.log1p(gap)),
            "log_prior_overall": float(np.log1p(self.n)),
            "acc_overall": _smoothed(self.k, self.n),
            "acc_overall_last10": _smoothed(sum(self.last10), len(self.last10)),
            "log_prior_item": float(np.log1p(i.n if i else 0)),
            "prev_item_correct": 1.0 if (i and i.k > 0) else 0.0,
        }
        if use_time:
            if now is None:
                raise ValueError("use_time=True needs the current time")
            since_c = (now - c.last_time).total_seconds() if c and c.last_time else 0.0
            since_any = (now - self.last_time).total_seconds() if self.last_time else 0.0
            row["log_secs_since_concept"] = float(np.log1p(max(since_c, 0.0)))
            row["log_secs_since_any"] = float(np.log1p(max(since_any, 0.0)))
        return row
