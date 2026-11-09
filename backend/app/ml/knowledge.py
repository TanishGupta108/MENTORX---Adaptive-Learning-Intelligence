"""Turn a student's answer history into P(correct) predictions and mastery estimates.

Uses the SAME feature code as training (mentorx_ml.serve, proven equal to the training
features by ml/tests/test_serve.py). Only the difficulty features are MENTORX-specific,
because MENTORX's questions have no history at launch (see `difficulty`).
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from mentorx_ml.serve import StudentState
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Attempt, Concept, Question
from app.ml.registry import LoadedModel

# Cold-start difficulty: what share of students the AUTHOR expects to answer correctly.
# An assumption, replaced by real data as answers accumulate (smoothing below), and to be
# recalibrated from pilot data (M11). The mid value matches the training data's average (~0.65).
AUTHOR_PRIOR = {1: 0.80, 2: 0.65, 3: 0.50}
M_ITEM = 10.0  # same smoothing strengths as training (mentorx_ml.features.DifficultyTable)
M_CONCEPT = 20.0


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return float(np.log(p / (1 - p)))


@dataclass
class Difficulty:
    item_logit: float
    concept_logit: float
    log_item_count: float

    def as_row(self) -> dict[str, float]:
        return {
            "item_logit": self.item_logit,
            "concept_logit": self.concept_logit,
            "log_item_count": self.log_item_count,
        }


def load_history(db: Session, user_id: uuid.UUID, subject_id: int) -> StudentState:
    rows = db.execute(
        select(Concept.code, Question.external_id, Attempt.is_correct, Attempt.created_at)
        .join(Question, Question.id == Attempt.question_id)
        .join(Concept, Concept.id == Question.concept_id)
        .where(Attempt.user_id == user_id, Concept.subject_id == subject_id)
        .order_by(Attempt.created_at, Attempt.id)
    ).all()
    return StudentState.from_history([(c, q, int(ok), ts) for c, q, ok, ts in rows])


def difficulty(
    db: Session, questions: list[Question], exclude_user: uuid.UUID
) -> tuple[dict[int, Difficulty], dict[int, Difficulty]]:
    """Smoothed difficulty per question and a "typical question" reference per concept.

    Answers from OTHER students only (mirrors the cross-fitting used in training).
    item p    = (k_item + M_ITEM * item_prior) / (n_item + M_ITEM)
    concept p = (k_concept + M_CONCEPT * concept_prior) / (n_concept + M_CONCEPT)
    where the priors come from the author ratings, and the item prior is shifted by how
    far the concept's real data has moved from its own author prior.
    """
    concept_ids = {q.concept_id for q in questions}
    if not concept_ids:
        return {}, {}
    stats = _all_student_stats(db)
    own_items, own_concepts = _own_stats(db, exclude_user, stats.max_attempt_id)

    def minus(total: tuple[int, int], own: tuple[int, int]) -> tuple[int, int]:
        return max(total[0] - own[0], 0), max(total[1] - own[1], 0)

    item_stats = {
        q.external_id: minus(
            stats.items.get(q.external_id, (0, 0)), own_items.get(q.external_id, (0, 0))
        )
        for q in questions
    }
    concept_stats = {
        cid: minus(stats.concepts.get(cid, (0, 0)), own_concepts.get(cid, (0, 0)))
        for cid in concept_ids
    }
    author_mean = {cid: stats.author_mean[cid] for cid in concept_ids if cid in stats.author_mean}

    concept_p: dict[int, float] = {}
    for cid in concept_ids:
        prior = author_mean.get(cid, AUTHOR_PRIOR[2])
        n, k = concept_stats.get(cid, (0, 0))
        concept_p[cid] = (k + M_CONCEPT * prior) / (n + M_CONCEPT)

    per_item: dict[int, Difficulty] = {}
    item_counts: dict[int, list[int]] = {cid: [] for cid in concept_ids}
    for q in questions:
        shift = concept_p[q.concept_id] - author_mean.get(q.concept_id, AUTHOR_PRIOR[2])
        prior = min(max(AUTHOR_PRIOR[q.author_difficulty] + shift, 0.02), 0.98)
        n, k = item_stats.get(q.external_id, (0, 0))
        item_counts[q.concept_id].append(n)
        per_item[q.id] = Difficulty(
            item_logit=_logit((k + M_ITEM * prior) / (n + M_ITEM)),
            concept_logit=_logit(concept_p[q.concept_id]),
            log_item_count=float(np.log1p(n)),
        )
    reference = {
        cid: Difficulty(
            item_logit=_logit(concept_p[cid]),
            concept_logit=_logit(concept_p[cid]),
            log_item_count=float(np.log1p(np.median(item_counts[cid]) if item_counts[cid] else 0)),
        )
        for cid in concept_ids
    }
    return per_item, reference


def predict_questions(
    db: Session,
    model: LoadedModel,
    user_id: uuid.UUID,
    subject_id: int,
    questions: list[Question],
    concept_codes: dict[int, str],
    now: datetime,
    state: StudentState | None = None,
) -> np.ndarray:
    """P(correct) for each candidate question if the student answered it now."""
    state = state or load_history(db, user_id, subject_id)
    diff, _ = difficulty(db, questions, user_id)
    rows = [
        {
            **state.history_row(concept_codes[q.concept_id], q.external_id, now, model.use_time),
            **diff[q.id].as_row(),
        }
        for q in questions
    ]
    return model.predict(rows)


REFERENCE_ITEM = "__typical_question__"


def concept_mastery(
    db: Session,
    model: LoadedModel,
    user_id: uuid.UUID,
    subject_id: int,
    concepts: list[Concept],
    now: datetime,
    state: StudentState | None = None,
) -> dict[int, float]:
    """Mastery = P(correct) on a typical, never-seen question of the concept, right now.

    Because time since practice is a feature, this decays when a concept isn't practised,
    which is what drives revision (FR-KT-04, design decision D-6).
    """
    at = concept_mastery_at(db, model, user_id, subject_id, concepts, [now], state)
    return {cid: ps[0] for cid, ps in at.items()}


# Without new answers, mastery is not allowed to RISE with the passage of time alone. Gradient
# boosting isn't monotone in the time features (measured: one student's estimate went 0.587
# at 30 days -> 0.600 at 90 days), which would make a concept due for revision and then
# not due again. So mastery at time t is the minimum of the model's predictions over these
# offsets after the student's last answer (any concept), up to t.
DECAY_GRID_DAYS = (
    1 / 24,
    0.25,
    1,
    2,
    3,
    5,
    7,
    10,
    14,
    21,
    30,
    45,
    60,
    90,
    120,
    180,
    270,
    365,
    540,
    730,
)


def concept_mastery_at(
    db: Session,
    model: LoadedModel,
    user_id: uuid.UUID,
    subject_id: int,
    concepts: list[Concept],
    times: list[datetime],
    state: StudentState | None = None,
) -> dict[int, list[float]]:
    """Mastery of each concept at each of `times`, assuming no further practice.

    One batched prediction for all (concept, time) pairs, including the decay-grid points
    (see DECAY_GRID_DAYS). Used for "now" and for projecting when a concept will be due
    for revision (FR-REV-05).
    """
    if not concepts or not times:
        return {}
    state = state or load_history(db, user_id, subject_id)
    questions = db.scalars(
        select(Question).where(
            Question.concept_id.in_([c.id for c in concepts]), Question.status == "active"
        )
    ).all()
    _, reference = difficulty(db, list(questions), user_id)

    grid: list[datetime] = []
    if model.use_time and state.last_time is not None:
        horizon = max(times)
        grid = [g for d in DECAY_GRID_DAYS if (g := state.last_time + timedelta(days=d)) < horizon]
    points = sorted(set(grid) | set(times))

    rows, ids = [], []
    for c in concepts:
        ref = reference.get(c.id)
        if ref is None:
            continue
        ids.append(c.id)
        for t in points:
            rows.append(
                {**state.history_row(c.code, REFERENCE_ITEM, t, model.use_time), **ref.as_row()}
            )
    if not rows:
        return {}
    preds = np.asarray(model.predict(rows), dtype=float).reshape(len(ids), len(points))
    # running minimum over time, then read off the requested times
    envelope = np.minimum.accumulate(preds, axis=1)
    col = {t: i for i, t in enumerate(points)}
    return {cid: [float(envelope[k, col[t]]) for t in times] for k, cid in enumerate(ids)}


# ---------------------------------------------------------------- answer statistics cache
#
# `difficulty` needs, for each question and concept, how many OTHER students answered and how
# many were correct. Aggregating the whole attempts table on every request was the largest
# single cost of serving a question (M12 load test). Instead, totals over ALL students are
# cached for `difficulty_cache_seconds`, together with the highest attempt id they include.
# Each request subtracts the requesting student's own answers up to that same id, which is
# cheap (indexed by user) and exact for that snapshot. The only approximation: other students'
# newest answers are reflected up to `difficulty_cache_seconds` late.


@dataclass(frozen=True)
class _Stats:
    max_attempt_id: int
    items: dict[str, tuple[int, int]]  # external_id -> (answers, correct)
    concepts: dict[int, tuple[int, int]]  # concept_id -> (answers, correct)
    author_mean: dict[int, float]  # concept_id -> mean author prior of active questions
    at: float


_stats: _Stats | None = None
_stats_lock = threading.Lock()


def reset_stats_cache() -> None:
    global _stats
    with _stats_lock:
        _stats = None


def _correct():
    return func.sum(case((Attempt.is_correct, 1), else_=0))


def _all_student_stats(db: Session) -> _Stats:
    global _stats
    ttl = get_settings().difficulty_cache_seconds
    with _stats_lock:
        cached = _stats
    if cached is not None and time.monotonic() - cached.at < ttl:
        return cached
    max_id = db.scalar(select(func.max(Attempt.id))) or 0
    upto = Attempt.id <= max_id
    items = {
        ext: (int(n), int(k or 0))
        for ext, n, k in db.execute(
            select(Question.external_id, func.count(), _correct())
            .join(Attempt, Attempt.question_id == Question.id)
            .where(upto)
            .group_by(Question.external_id)
        )
    }
    concepts = {
        cid: (int(n), int(k or 0))
        for cid, n, k in db.execute(
            select(Question.concept_id, func.count(), _correct())
            .join(Attempt, Attempt.question_id == Question.id)
            .where(upto)
            .group_by(Question.concept_id)
        )
    }
    author_mean = {
        cid: float(m)
        for cid, m in db.execute(
            select(
                Question.concept_id,
                func.avg(
                    case(*((Question.author_difficulty == d, p) for d, p in AUTHOR_PRIOR.items()))
                ),
            )
            .where(Question.status == "active")
            .group_by(Question.concept_id)
        )
    }
    fresh = _Stats(max_id, items, concepts, author_mean, time.monotonic())
    with _stats_lock:
        _stats = fresh
    return fresh


def _own_stats(
    db: Session, user_id: uuid.UUID, max_attempt_id: int
) -> tuple[dict[str, tuple[int, int]], dict[int, tuple[int, int]]]:
    """The student's own answers included in the cached totals (ids up to the snapshot)."""
    rows = db.execute(
        select(Question.external_id, Question.concept_id, Attempt.is_correct)
        .join(Attempt, Attempt.question_id == Question.id)
        .where(Attempt.user_id == user_id, Attempt.id <= max_attempt_id)
    ).all()
    items: dict[str, list[int]] = {}
    concepts: dict[int, list[int]] = {}
    for ext, cid, ok in rows:
        for table, key in ((items, ext), (concepts, cid)):
            n_k = table.setdefault(key, [0, 0])
            n_k[0] += 1
            n_k[1] += int(ok)
    return (
        {k: (v[0], v[1]) for k, v in items.items()},
        {k: (v[0], v[1]) for k, v in concepts.items()},
    )
