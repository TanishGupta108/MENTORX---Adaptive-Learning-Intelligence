"""Assessments: the diagnostic, a single-skill check, and reassessment with fresh questions.

- Overall diagnostic: one question in each of `diagnostic_length` core skills, spread across
  domains and grades, using rated MEDIUM questions (the most informative difficulty), easiest
  grade first. A small random choice among comparable questions means two students don't get
  identical tests.
- Skill check: several questions from one chosen skill, easy -> hard.
- Reassessment: only questions the student has NEVER seen, so improvement is measured on
  fresh material. It compares the student's initial observed accuracy in the skill with the
  reassessment, and shows the model's estimate separately.
Immediate feedback (correct or not, plus the correct answer) is given after every answer.
"""

from __future__ import annotations

import random
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import User
from app.tutor import engine, kt, recommend, state
from app.tutor import profile as profile_service
from app.tutor.models import Assessment, Interaction, Item, Skill, SkillState

_rng = random.SystemRandom()
CORE_MIN_ITEMS = 20
DIFF_ORDER = {"easy": 0, "medium": 1, "hard": 2, "unrated": 1}


def _pick(cands: list[Item], target_rate: float = 0.6, k: int = 3) -> Item:
    ranked = sorted(cands, key=lambda i: abs((i.success_rate or 0.6) - target_rate))
    return _rng.choice(ranked[:k])


def plan_diagnostic(db: Session, n: int) -> list[int]:
    core = list(
        db.scalars(select(Skill).where(Skill.is_available, Skill.n_items >= CORE_MIN_ITEMS))
    )
    by_domain: dict[str, list[Skill]] = {}
    for s in sorted(core, key=lambda s: (s.grade or 0, -s.n_items)):
        by_domain.setdefault(s.domain_code, []).append(s)
    chosen: list[Skill] = []
    codes: set[str] = set()
    while len(chosen) < n and any(by_domain.values()):
        for dom in list(by_domain):
            while by_domain[dom] and by_domain[dom][0].code in codes:
                by_domain[dom].pop(0)  # one skill per standard code
            if by_domain[dom] and len(chosen) < n:
                s = by_domain[dom].pop(0)
                chosen.append(s)
                codes.add(s.code)
    items = []
    for s in sorted(chosen, key=lambda s: (s.grade or 0, s.code)):
        cands = list(db.scalars(engine.usable_items(db, s.id).where(Item.difficulty == "medium")))
        cands = cands or list(
            db.scalars(engine.usable_items(db, s.id).where(Item.difficulty != "unrated"))
        )
        if cands:
            items.append(_pick(cands).id)
    return items


def plan_skill(
    db: Session, user_id: uuid.UUID, skill_id: int, n: int, fresh_only: bool
) -> list[int]:
    seen = engine.attempted_item_ids(db, user_id)
    pool = [
        i
        for i in db.scalars(engine.usable_items(db, skill_id))
        if i.id not in seen or not fresh_only
    ]
    rated = [i for i in pool if i.difficulty != "unrated"] or pool
    _rng.shuffle(rated)
    # a spread of difficulties: mostly medium, at least one easy and one hard when available
    want = ["easy", "medium", "medium", "hard", "medium", "easy", "hard", "medium"] * 3
    picked: list[Item] = []
    for d in want:
        if len(picked) >= n:
            break
        nxt = next((i for i in rated if i.difficulty == d and i not in picked), None)
        if nxt:
            picked.append(nxt)
    for i in rated:  # top up if a level ran out
        if len(picked) >= n:
            break
        if i not in picked:
            picked.append(i)
    return [
        i.id
        for i in sorted(picked, key=lambda i: (DIFF_ORDER[i.difficulty], -(i.success_rate or 0.6)))
    ]


def _own(db: Session, user: User, assessment_id: uuid.UUID, lock: bool = False) -> Assessment:
    stmt = select(Assessment).where(Assessment.id == assessment_id, Assessment.user_id == user.id)
    if lock:
        stmt = stmt.with_for_update()
    a = db.scalar(stmt)
    if a is None:
        raise AppError(404, "assessment_not_found", "Assessment not found.")
    return a


def start(db: Session, user: User, kind: str, skill_id: int | None) -> Assessment:
    cfg = get_settings()
    prof = profile_service.require(db, user)
    active = db.scalar(
        select(Assessment)
        .where(Assessment.user_id == user.id, Assessment.status == "active")
        .with_for_update()
    )
    if active:
        if active.kind == kind and active.skill_id == skill_id:
            return active  # resume
        active.status = "abandoned"
        active.completed_at = engine.now()
    skill = None
    if kind != "diagnostic":
        skill = db.get(Skill, skill_id) if skill_id else None
        if skill is None or not skill.is_available:
            raise AppError(404, "skill_not_found", "That skill isn't available.")
    if kind == "diagnostic":
        planned = plan_diagnostic(db, cfg.diagnostic_length)
    elif kind == "skill_check":
        planned = plan_skill(db, user.id, skill.id, cfg.skill_check_length, fresh_only=True)
    else:
        planned = plan_skill(db, user.id, skill.id, cfg.reassessment_length, fresh_only=True)
        if len(planned) < 3:
            raise AppError(
                409,
                "not_enough_fresh_questions",
                "You've already seen almost every question in this skill, so a fair reassessment "
                "isn't possible. Keep practising instead.",
            )
    if not planned:
        raise AppError(409, "no_content", "There are no questions available for this assessment.")
    snapshot = {}
    if skill is not None:
        st = db.get(SkillState, (user.id, skill.id))
        c, n = engine.skill_accuracy(db, user.id, skill.id)
        snapshot = {
            "before": {"correct": c, "attempts": n, "predicted_p": st.predicted_p if st else None}
        }
    a = Assessment(
        user_id=user.id,
        subject_id=prof.subject_id,
        kind=kind,
        skill_id=skill.id if skill else None,
        planned_item_ids=planned,
        result=snapshot,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def to_out(db: Session, a: Assessment) -> dict:
    skill = db.get(Skill, a.skill_id) if a.skill_id else None
    return {
        "id": a.id,
        "kind": a.kind,
        "status": a.status,
        "skill": {"id": skill.id, "name": skill.name, "code": skill.code} if skill else None,
        "answered": a.answered_count,
        "correct": a.correct_count,
        "total": a.target_count,
        "started_at": a.started_at,
        "completed_at": a.completed_at,
        "result": a.result if a.status == "completed" else None,
    }


def next_item(db: Session, user: User, assessment_id: uuid.UUID) -> dict:
    a = _own(db, user, assessment_id, lock=True)
    if a.status != "active":
        raise AppError(409, "assessment_closed", "This assessment has finished.")
    if a.current_item_id is None:
        done = set(db.scalars(select(Interaction.item_id).where(Interaction.assessment_id == a.id)))
        remaining = [i for i in a.planned_item_ids if i not in done]
        if not remaining:
            raise AppError(409, "assessment_complete", "No questions left.")
        item = db.get(Item, remaining[0])
        h = kt.state_for(db, user.id)
        a.current_item_id = item.id
        a.current_served_at = engine.now()
        a.current_predicted_p = kt.predict_items(h, [item])[0]
        db.commit()
    item = db.get(Item, a.current_item_id)
    return engine.public_item(db, item, a.answered_count + 1, a.target_count)


def answer(db: Session, user: User, assessment_id: uuid.UUID, item_id: int, response: dict) -> dict:
    a = _own(db, user, assessment_id, lock=True)
    if a.status != "active":
        raise AppError(409, "assessment_closed", "This assessment has finished.")
    if a.current_item_id != item_id:
        raise AppError(409, "question_mismatch", "That isn't the question currently shown.")
    item = db.get(Item, item_id)
    inter = engine.record(
        db,
        user.id,
        item,
        response,
        context="assessment",
        served_at=a.current_served_at,
        predicted_p=a.current_predicted_p,
        assessment_id=a.id,
    )
    a.answered_count += 1
    a.correct_count += int(inter.is_correct)
    a.current_item_id = a.current_served_at = a.current_predicted_p = None
    complete = a.answered_count >= a.target_count
    result = None
    if complete:
        result = finish(db, user, a)
    else:
        state.refresh(db, user.id)
    db.commit()
    return {
        "correct": inter.is_correct,
        "correct_answer": engine.reveal(item),
        "message": "Correct. Nice work!"
        if inter.is_correct
        else "Not quite. That's useful information for your plan.",
        "answered": a.answered_count,
        "total": a.target_count,
        "complete": complete,
        "result": result,
    }


def finish(db: Session, user: User, a: Assessment) -> dict:
    cfg = get_settings()
    t = engine.now()
    a.status, a.completed_at = "completed", t
    states = state.refresh(db, user.id, t)
    prof = profile_service.require(db, user)
    result = dict(a.result or {})
    result.update(
        {
            "accuracy": a.correct_count / max(a.answered_count, 1),
            "correct": a.correct_count,
            "answered": a.answered_count,
        }
    )
    if a.kind == "diagnostic":
        prof.diagnostic_completed_at = prof.diagnostic_completed_at or t
        counts: dict[str, int] = {}
        for st in states.values():
            counts[st.status] = counts.get(st.status, 0) + 1
        result["status_counts"] = counts
        trigger = "diagnostic"
    elif a.kind == "skill_check":
        prof.diagnostic_completed_at = prof.diagnostic_completed_at or t
        trigger = "skill_check"
    else:
        result.update(_reassessment_outcome(db, user.id, a, states.get(a.skill_id), cfg))
        trigger = "reassessment"
    a.result = result
    recommend.generate(db, user.id, trigger, t)
    return result


def _reassessment_outcome(
    db: Session, user_id: uuid.UUID, a: Assessment, st: SkillState | None, cfg
) -> dict:
    """Initial observed accuracy (first answers in the skill, before this reassessment) vs now."""
    before_rows = (
        db.execute(
            select(Interaction.is_correct)
            .where(
                Interaction.user_id == user_id,
                Interaction.skill_id == a.skill_id,
                Interaction.created_at < a.started_at,
            )
            .order_by(Interaction.created_at, Interaction.id)
            .limit(5)
        )
        .scalars()
        .all()
    )
    initial = sum(before_rows) / len(before_rows) if before_rows else None
    recent = a.correct_count / max(a.answered_count, 1)
    if recent >= cfg.reassessment_pass or (
        recent >= 0.7 and initial is not None and recent - initial >= cfg.improvement_margin
    ):
        outcome = "improved"
    elif initial is not None and recent - initial >= cfg.improvement_margin:
        outcome = "progressing"
    else:
        outcome = "not_improved"
    if st is not None:
        st.reassessed_accuracy = recent
        if recent >= cfg.reassessment_pass:
            st.completed_at = engine.now()
            st.revision_due_at = engine.now() + timedelta(days=cfg.revision_after_days)
        if outcome == "not_improved":
            st.mode_override = None  # let the evidence-based mode step down to more support
    before = (a.result or {}).get("before", {})
    return {
        "initial_accuracy": initial,
        "initial_attempts": len(before_rows),
        "reassessment_accuracy": recent,
        "outcome": outcome,
        "predicted_before": before.get("predicted_p"),
        "predicted_after": st.predicted_p if st else None,
        "completed": bool(st and st.completed_at and recent >= cfg.reassessment_pass),
        "revision_due_at": st.revision_due_at.isoformat() if st and st.revision_due_at else None,
    }


def list_for(db: Session, user: User, limit: int = 30) -> list[dict]:
    rows = db.scalars(
        select(Assessment)
        .where(Assessment.user_id == user.id)
        .order_by(Assessment.started_at.desc())
        .limit(limit)
    )
    return [to_out(db, a) for a in rows]


def get(db: Session, user: User, assessment_id: uuid.UUID) -> dict:
    return to_out(db, _own(db, user, assessment_id))
