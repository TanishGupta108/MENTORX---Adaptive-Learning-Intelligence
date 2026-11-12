"""Per-skill learning state: evidence, diagnosis, learning mode (pure rules + one refresher).

Principles (from the product brief):
- Observed performance and model prediction are different things and are stored and shown
  separately. A model probability is never presented as mastery.
- No evidence -> "Needs Assessment", whatever the model predicts. A skill is only called a
  weakness or a strength when the student's own answers support it.
- Learning modes are per skill and change as evidence changes. Speed is never used to judge
  understanding.
- Only single-skill questions are evidence for a skill. A multi-skill question has one shared
  score, so it is never counted for each of its skills (the model still sees it, with all of
  its skills, because that is how it was trained).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.tutor import kt
from app.tutor.models import Interaction, Skill, SkillState, StudentProfile

MODES = ["foundation", "guided", "independent", "advanced"]
RECENT_WINDOW = 6

# What each mode means for practice: starting difficulty and the success rate we aim for
# when choosing among questions with the model (easier modes aim for more success).
MODE_POLICY = {
    "foundation": {"start": "easy", "target_p": 0.80, "hints": "offered"},
    "guided": {"start": "easy", "target_p": 0.70, "hints": "offered"},
    "independent": {"start": "medium", "target_p": 0.60, "hints": "on request"},
    "advanced": {"start": "hard", "target_p": 0.50, "hints": "on request"},
}


@dataclass(frozen=True)
class Evidence:
    attempts: int
    correct: int
    recent: list[int]  # most recent last, 1 = correct
    hints: int = 0

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.attempts if self.attempts else None

    @property
    def recent_accuracy(self) -> float | None:
        r = self.recent[-RECENT_WINDOW:]
        return sum(r) / len(r) if r else None


def evidence_level(attempts: int) -> str:
    if attempts == 0:
        return "none"
    if attempts <= 2:
        return "limited"
    if attempts <= 5:
        return "moderate"
    return "strong"


def diagnose(ev: Evidence, predicted: float | None, strength: float, weakness: float) -> str:
    """One of likely_strength / developing / potential_weakness / needs_assessment."""
    acc = ev.recent_accuracy
    if acc is None:
        return "needs_assessment"  # never call a skill weak (or strong) on the model alone
    model_agrees_strong = predicted is None or predicted >= 0.6
    model_agrees_weak = predicted is None or predicted < 0.6
    if acc >= strength and ev.attempts >= 2 and model_agrees_strong:
        return "likely_strength"
    if acc <= weakness and model_agrees_weak:
        return "potential_weakness"
    return "developing"


def learning_mode(ev: Evidence, predicted: float | None, pace: str = "balanced") -> str:
    """Per-skill mode from accuracy, hint use and evidence (never from speed)."""
    if ev.attempts < 2:
        if predicted is None:
            level = 1
        else:
            level = 0 if predicted < 0.45 else 1 if predicted < 0.65 else 2
    else:
        r = ev.recent[-RECENT_WINDOW:]
        hint_rate = min(ev.hints / ev.attempts, 1.0)
        score = (sum(r) / len(r)) - 0.25 * hint_rate  # needing hints means less independence
        if score < 0.4:
            level = 0
        elif score < 0.65:
            level = 1
        elif score < 0.85 or ev.attempts < 5:
            level = 2
        else:
            level = 3
    level += {"more_support": -1, "balanced": 0, "challenge": 1}.get(pace, 0)
    return MODES[max(0, min(3, level))]


def effective_mode(state: SkillState) -> str:
    return state.mode_override or state.mode


def _evidence_from_rows(rows: list[tuple[bool, bool]]) -> Evidence:
    labels = [int(c) for c, _ in rows]
    return Evidence(
        attempts=len(rows),
        correct=sum(labels),
        recent=labels[-10:],
        hints=sum(int(h) for _, h in rows),
    )


def evidence_for(db: Session, user_id: uuid.UUID, skill_id: int) -> Evidence:
    rows = db.execute(
        select(Interaction.is_correct, Interaction.hint_used)
        .where(
            Interaction.user_id == user_id,
            Interaction.skill_id == skill_id,
            Interaction.n_skills == 1,
        )
        .order_by(Interaction.created_at, Interaction.id)
    ).all()
    return _evidence_from_rows([(c, h) for c, h in rows])


def refresh(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> dict[int, SkillState]:
    """Recompute every available skill's state from the interaction log and the model.

    Observed numbers come only from the student's answers; `predicted_p` only from the model.
    """
    cfg = get_settings()
    now = now or datetime.now(UTC)
    profile = db.get(StudentProfile, user_id)
    pace = profile.pace_preference if profile else "balanced"
    skills = list(db.scalars(select(Skill).where(Skill.is_available)))
    rows = db.execute(
        select(
            Interaction.skill_id,
            Interaction.is_correct,
            Interaction.hint_used,
            Interaction.created_at,
        )
        .where(Interaction.user_id == user_id, Interaction.n_skills == 1)  # see module doc
        .order_by(Interaction.created_at, Interaction.id)
    ).all()
    by_skill: dict[int, list[tuple[bool, bool]]] = {}
    last: dict[int, datetime] = {}
    for sid, c, h, ts in rows:
        by_skill.setdefault(sid, []).append((c, h))
        last[sid] = ts
    preds = kt.skill_predictions(db, user_id)
    model = kt.get_model()
    states = {
        s.skill_id: s for s in db.scalars(select(SkillState).where(SkillState.user_id == user_id))
    }
    for skill in skills:
        ev = _evidence_from_rows(by_skill.get(skill.id, []))
        st = states.get(skill.id)
        if st is None:
            st = SkillState(user_id=user_id, skill_id=skill.id, recent=[])
            db.add(st)
            states[skill.id] = st
        p = preds.get(skill.id)
        st.attempts, st.correct, st.hints_used, st.recent = (
            ev.attempts,
            ev.correct,
            ev.hints,
            ev.recent,
        )
        st.predicted_p = p
        st.model_name = model.name if (model and p is not None) else None
        st.evidence = evidence_level(ev.attempts)
        st.status = diagnose(ev, p, cfg.strength_threshold, cfg.weakness_threshold)
        st.mode = learning_mode(ev, p, pace)
        st.last_practiced_at = last.get(skill.id)
        st.updated_at = now
    db.flush()
    return states
