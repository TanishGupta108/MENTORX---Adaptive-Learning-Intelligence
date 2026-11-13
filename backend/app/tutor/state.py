"""Per-skill learning state: evidence, diagnosis, mastery, learning mode (pure rules + one
refresher per subject).

Principles (from the product brief):
- Observed performance and model prediction are different things and are stored and shown
  separately. A model probability is never presented as mastery.
- No evidence -> "Needs Assessment" ("Not tried yet"), whatever the model predicts. A skill is
  only called a weakness or a strength when the student's own answers support it.
- Learning modes are per skill and change as evidence changes. Speed is never used to judge
  understanding.
- Only single-skill questions are evidence for a skill. A multi-skill question has one shared
  score, so it is never counted for each of its skills (the model still sees it, with all of
  its skills, because that is how it was trained).

Rules (thresholds live in config):
- Mastery: the last 3 answers correct AND >= 80% of the last 8 correct AND >= 5 answers.
  `to_go` = how many more correct answers in a row would meet it.
- Stuck (wheel-spinning): >= 10 answers without ever meeting the mastery rule AND fewer than
  half of the last 6 correct.
- Review schedule: when a skill first becomes Strong (or is completed) a review is due 3 days
  later; each successful review moves along REVIEW_INTERVALS (3, 7, 14, 30, 60 days).
- Completed: normally by passing a check made only of questions the student has never seen
  (reassessment, at least CHECK_MIN_FRESH of them). When fewer than CHECK_MIN_FRESH unseen
  questions are left in the skill, a fresh check can't be fair, so the skill is completed by
  the mastery rule alone (`refresh`). The check never reuses seen questions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Subject
from app.tutor import kt
from app.tutor.models import Interaction, Item, Skill, SkillState, StudentProfile

MODES = ["foundation", "guided", "independent", "advanced"]
RECENT_WINDOW = 6
REVIEW_INTERVALS = [3, 7, 14, 30, 60]
CHECK_MIN_FRESH = 3  # unseen questions a fresh check (reassessment) needs

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
    recent_hints: list[int] = field(default_factory=list)  # most recent last, 1 = hint used

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


def review_interval(stage: int) -> int:
    return REVIEW_INTERVALS[max(0, min(stage, len(REVIEW_INTERVALS) - 1))]


# ---------------------------------------------------------------- mastery and stuck


def mastery_met(recent: list[int], attempts: int, cfg=None) -> bool:
    """Observed mastery rule on the most recent answers (most recent last)."""
    cfg = cfg or get_settings()
    if attempts < cfg.mastery_min_attempts or len(recent) < cfg.mastery_streak:
        return False
    if any(x != 1 for x in recent[-cfg.mastery_streak :]):
        return False
    window = recent[-cfg.mastery_window :]
    return sum(window) / len(window) >= cfg.mastery_rate


def to_go(recent: list[int], attempts: int, cfg=None) -> int | None:
    """Smallest k (0..10) such that k more correct answers meet the mastery rule."""
    cfg = cfg or get_settings()
    for k in range(11):
        if mastery_met([*recent, *([1] * k)], attempts + k, cfg):
            return k
    return None


def ever_mastered_at(seq: list[tuple[int, datetime]], cfg=None) -> datetime | None:
    """When the mastery rule first held over a full answer sequence (or None)."""
    cfg = cfg or get_settings()
    labels: list[int] = []
    for i, (c, ts) in enumerate(seq):
        labels.append(c)
        if mastery_met(labels[-max(cfg.mastery_window, cfg.mastery_streak) :], i + 1, cfg):
            return ts
    return None


def is_stuck(attempts: int, recent: list[int], mastered_at: datetime | None, cfg=None) -> bool:
    cfg = cfg or get_settings()
    r = recent[-RECENT_WINDOW:]
    return (
        attempts >= cfg.stuck_min_attempts
        and mastered_at is None
        and bool(r)
        and sum(r) / len(r) < cfg.stuck_recent_rate
    )


def mastery_info(st: SkillState | None, cfg=None) -> dict:
    """{mastered, to_go, stuck, progress_hint} for the API (observed answers only)."""
    cfg = cfg or get_settings()
    if st is None or st.attempts == 0:
        return {"mastered": False, "to_go": None, "stuck": False, "progress_hint": None}
    recent = list(st.recent or [])
    mastered = mastery_met(recent, st.attempts, cfg)
    k = 0 if mastered else to_go(recent, st.attempts, cfg)
    stuck = is_stuck(st.attempts, recent, st.mastered_at, cfg)
    if st.completed_at:
        hint = "Completed"
    elif mastered:
        hint = f"Mastered: take the {cfg.reassessment_length}-question check"
    elif k is not None:
        hint = f"{k} more correct to master"
    else:
        hint = None
    return {"mastered": mastered, "to_go": k, "stuck": stuck, "progress_hint": hint}


# ---------------------------------------------------------------- diagnosis and mode


def diagnose(
    ev: Evidence,
    predicted: float | None,
    strength: float,
    weakness: float,
    agree: float | None = None,
) -> str:
    """One of likely_strength / developing / potential_weakness / needs_assessment."""
    agree = get_settings().model_agree_threshold if agree is None else agree
    acc = ev.recent_accuracy
    if acc is None:
        return "needs_assessment"  # never call a skill weak (or strong) on the model alone
    model_agrees_strong = predicted is None or predicted >= agree
    model_agrees_weak = predicted is None or predicted < agree
    if acc >= strength and ev.attempts >= 2 and model_agrees_strong:
        return "likely_strength"
    if acc <= weakness and ev.attempts >= 2 and model_agrees_weak:
        return "potential_weakness"  # one wrong answer is not enough evidence of a weakness
    return "developing"


def learning_mode(ev: Evidence, predicted: float | None, pace: str = "balanced") -> str:
    """Per-skill mode from recent accuracy and recent hint use (never from speed)."""
    if ev.attempts < 2:
        if predicted is None:
            level = 1
        else:
            level = 0 if predicted < 0.45 else 1 if predicted < 0.65 else 2
    else:
        r = ev.recent[-RECENT_WINDOW:]
        h = (ev.recent_hints or [])[-RECENT_WINDOW:]
        hint_rate = sum(h) / len(h) if h else 0.0
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
    hints = [int(h) for _, h in rows]
    return Evidence(
        attempts=len(rows),
        correct=sum(labels),
        recent=labels[-10:],
        hints=sum(hints),
        recent_hints=hints[-10:],
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


# ---------------------------------------------------------------- fresh-check eligibility


def fresh_counts(db: Session, user_id: uuid.UUID, skill_ids) -> dict[int, int]:
    """Usable single-skill questions the student has never seen, per skill (one query)."""
    ids = list(skill_ids)
    if not ids:
        return {}
    seen = select(Interaction.item_id).where(Interaction.user_id == user_id)
    rows = db.execute(
        select(Item.skill_id, func.count())
        .where(
            Item.skill_id.in_(ids),
            Item.n_skills == 1,
            Item.is_active,
            Item.exclusion_reason.is_(None),
            Item.id.not_in(seen),
        )
        .group_by(Item.skill_id)
    ).all()
    return {sid: 0 for sid in ids} | {sid: int(n) for sid, n in rows}


def can_check(db: Session, user_id: uuid.UUID, skill_id: int) -> bool:
    """The ONE rule for offering and starting a reassessment ("Take the short check")."""
    return fresh_counts(db, user_id, [skill_id])[skill_id] >= CHECK_MIN_FRESH


# ---------------------------------------------------------------- pace suggestion


PACE_MESSAGES = {
    "challenge": "You're getting most questions right without hints. Want harder questions?",
    "more_support": "These questions have been tough lately. Want easier steps and more hints?",
}


def pace_suggestion(rows: list[tuple[bool, bool, bool, str]], current: str, cfg=None) -> str | None:
    """rows = the most recent single-skill answers, newest LAST: (correct, hint, revealed,
    session key). Suggests a pace only with a full window from at least two sessions."""
    cfg = cfg or get_settings()
    rows = rows[-cfg.pace_window :]
    if len(rows) < cfg.pace_window or len({r[3] for r in rows}) < 2:
        return None
    n = len(rows)
    acc = sum(int(r[0]) for r in rows) / n
    hint_rate = sum(int(r[1]) for r in rows) / n
    reveal_rate = sum(int(r[2]) for r in rows) / n
    if acc >= 0.85 and hint_rate < 0.10 and current != "challenge":
        return "challenge"
    if (acc < 0.5 or reveal_rate > 0.30) and current != "more_support":
        return "more_support"
    return None


# ---------------------------------------------------------------- refresh


def _subject(db: Session, user_id: uuid.UUID, subject_id: int | None) -> Subject | None:
    if subject_id is None:
        profile = db.get(StudentProfile, user_id)
        subject_id = profile.subject_id if profile else None
    if subject_id is None:
        return db.scalar(select(Subject).where(Subject.code == "MATH"))
    return db.get(Subject, subject_id)


def refresh(
    db: Session,
    user_id: uuid.UUID,
    subject_id: int | None = None,
    now: datetime | None = None,
) -> dict[int, SkillState]:
    """Recompute every available skill's state IN ONE SUBJECT (default: the student's current
    subject) from the interaction log and that subject's model.

    Observed numbers come only from the student's answers; `predicted_p` only from the model.
    """
    cfg = get_settings()
    now = now or datetime.now(UTC)
    subject = _subject(db, user_id, subject_id)
    if subject is None:
        return {}
    profile = db.get(StudentProfile, user_id)
    pace = profile.pace_preference if profile else "balanced"
    skills = list(
        db.scalars(select(Skill).where(Skill.subject_id == subject.id, Skill.is_available))
    )
    rows = db.execute(
        select(
            Interaction.skill_id,
            Interaction.is_correct,
            Interaction.hint_used,
            Interaction.created_at,
        )
        .join(Skill, Skill.id == Interaction.skill_id)
        .where(
            Interaction.user_id == user_id,
            Interaction.n_skills == 1,  # see module doc
            Skill.subject_id == subject.id,
        )
        .order_by(Interaction.created_at, Interaction.id)
    ).all()
    by_skill: dict[int, list[tuple[bool, bool, datetime]]] = {}
    for sid, c, h, ts in rows:
        by_skill.setdefault(sid, []).append((c, h, ts))
    preds = kt.skill_predictions(db, user_id, subject.id, subject.code)
    model = kt.get_model(subject.code)
    states = {
        s.skill_id: s
        for s in db.scalars(
            select(SkillState)
            .join(Skill, Skill.id == SkillState.skill_id)
            .where(SkillState.user_id == user_id, Skill.subject_id == subject.id)
        )
    }
    for skill in skills:
        seq = by_skill.get(skill.id, [])
        ev = _evidence_from_rows([(c, h) for c, h, _ in seq])
        st = states.get(skill.id)
        if st is None:
            st = SkillState(user_id=user_id, skill_id=skill.id, recent=[], revision_stage=0)
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
        st.status = diagnose(
            ev, p, cfg.strength_threshold, cfg.weakness_threshold, cfg.model_agree_threshold
        )
        st.mode = learning_mode(ev, p, pace)
        if st.mastered_at is None and seq:
            st.mastered_at = ever_mastered_at([(int(c), ts) for c, _, ts in seq], cfg)
        if st.revision_due_at is None and (st.status == "likely_strength" or st.completed_at):
            st.revision_stage = st.revision_stage or 0
            st.revision_due_at = now + timedelta(days=REVIEW_INTERVALS[0])
        st.last_practiced_at = seq[-1][2] if seq else None
        st.updated_at = now
    # mastered, but too few unseen questions for a fair fresh check: completed by mastery
    pending = [
        sid
        for sid, st in states.items()
        if st.attempts
        and st.completed_at is None
        and mastery_met(list(st.recent or []), st.attempts, cfg)
    ]
    for sid, n in fresh_counts(db, user_id, pending).items():
        if n < CHECK_MIN_FRESH:
            st = states[sid]
            st.completed_at = now
            st.revision_stage = st.revision_stage or 0
            st.revision_due_at = st.revision_due_at or now + timedelta(days=REVIEW_INTERVALS[0])
    db.flush()
    return states
