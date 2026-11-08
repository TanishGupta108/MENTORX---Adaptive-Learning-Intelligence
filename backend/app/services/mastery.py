"""Store mastery estimates and their history (FR-KT-03)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Attempt, Concept, Mastery, MasterySnapshot, Question
from app.ml import knowledge
from app.ml.registry import LoadedModel


def _attempt_counts(db: Session, user_id: uuid.UUID, concept_ids: list[int]) -> dict[int, tuple]:
    return {
        cid: (int(n), last)
        for cid, n, last in db.execute(
            select(Question.concept_id, func.count(), func.max(Attempt.created_at))
            .join(Attempt, Attempt.question_id == Question.id)
            .where(Attempt.user_id == user_id, Question.concept_id.in_(concept_ids))
            .group_by(Question.concept_id)
        )
    }


def recompute(
    db: Session,
    model: LoadedModel,
    user_id: uuid.UUID,
    subject_id: int,
    concepts: list[Concept],
    now: datetime,
    attempt_id: int | None = None,
) -> dict[int, tuple[float | None, float]]:
    """Recompute and store mastery for `concepts`. Returns {concept_id: (before, after)}."""
    if not concepts:
        return {}
    ids = [c.id for c in concepts]
    before = {
        m.concept_id: m.p_mastery
        for m in db.scalars(
            select(Mastery).where(Mastery.user_id == user_id, Mastery.concept_id.in_(ids))
        )
    }
    after = knowledge.concept_mastery(db, model, user_id, subject_id, concepts, now)
    counts = _attempt_counts(db, user_id, ids)
    for cid, p in after.items():
        n, last = counts.get(cid, (0, None))
        stmt = insert(Mastery).values(
            user_id=user_id,
            concept_id=cid,
            p_mastery=p,
            peak_mastery=p,
            n_attempts=n,
            last_attempt_at=last,
            model_version_id=model.version_id,
            updated_at=now,
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["user_id", "concept_id"],
                set_={
                    "p_mastery": p,
                    # peak only counts once the student has actually practised (revision rule)
                    "peak_mastery": func.greatest(Mastery.peak_mastery, p) if n else p,
                    "n_attempts": n,
                    "last_attempt_at": last,
                    "model_version_id": model.version_id,
                    "updated_at": now,
                },
            )
        )
        db.add(MasterySnapshot(user_id=user_id, concept_id=cid, p_mastery=p, attempt_id=attempt_id))
    return {cid: (before.get(cid), p) for cid, p in after.items()}


@dataclass
class ConceptState:
    """A concept's mastery as of now, for recommendations and dashboards."""

    concept: Concept
    p: float  # current mastery (model estimate, fresh within mastery_stale_hours)
    peak: float | None  # highest stored mastery; None if never stored
    n_attempts: int
    last_attempt_at: datetime | None

    @property
    def attempted(self) -> bool:
        return self.n_attempts > 0


def current(
    db: Session,
    model: LoadedModel,
    user_id: uuid.UUID,
    subject_id: int,
    concepts: list[Concept],
    now: datetime,
) -> dict[int, ConceptState]:
    """Current mastery for every concept (FR-KT-04).

    Stored values older than `mastery_stale_hours` are recomputed and saved, so displayed
    mastery decays between visits. Concepts with no stored value get a model estimate that is
    NOT saved (nothing has been learnt about them yet). The caller commits.
    """
    ids = [c.id for c in concepts]
    rows = {
        m.concept_id: m
        for m in db.scalars(
            select(Mastery).where(Mastery.user_id == user_id, Mastery.concept_id.in_(ids))
        )
    }
    cutoff = now - timedelta(hours=get_settings().mastery_stale_hours)
    stale = [c for c in concepts if c.id in rows and rows[c.id].updated_at < cutoff]
    if stale:
        recompute(db, model, user_id, subject_id, stale, now)
        db.flush()
        for m in db.scalars(
            select(Mastery)
            .where(Mastery.user_id == user_id, Mastery.concept_id.in_([c.id for c in stale]))
            .execution_options(populate_existing=True)
        ):
            rows[m.concept_id] = m
    missing = [c for c in concepts if c.id not in rows]
    estimates = (
        knowledge.concept_mastery(db, model, user_id, subject_id, missing, now) if missing else {}
    )
    out: dict[int, ConceptState] = {}
    for c in concepts:
        if c.id in rows:
            m = rows[c.id]
            out[c.id] = ConceptState(
                c, m.p_mastery, m.peak_mastery, m.n_attempts, m.last_attempt_at
            )
        elif c.id in estimates:
            out[c.id] = ConceptState(c, estimates[c.id], None, 0, None)
    return out
