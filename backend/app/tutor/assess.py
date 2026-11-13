"""Assessments: the diagnostic (placement check), a single-skill check, and reassessment with
fresh questions. Every assessment belongs to one subject.

- Diagnostic: adaptive, one question at a time across the subject's core skills (see
  choose_diagnostic_item). It starts near the student's grade (grade - 1, at least 3).
- Skill check: several questions from one chosen skill, easy -> hard.
- Reassessment: only questions the student has NEVER seen, so improvement is measured on
  fresh material. It needs at least state.CHECK_MIN_FRESH of them (`state.can_check`, the same
  rule every "Take the short check" button uses); a skill with fewer left is completed by the
  mastery rule instead (state.refresh). It compares the student's initial observed accuracy in the skill (single-skill
  answers only) with the reassessment, and shows the model's estimate separately.
Immediate feedback (correct or not, plus the correct answer) is given after every answer.
"""

from __future__ import annotations

import random
import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import Subject, User
from app.tutor import engine, kt, recommend, state
from app.tutor import profile as profile_service
from app.tutor.models import (
    Assessment,
    Interaction,
    Item,
    Skill,
    SkillPrerequisite,
    SkillState,
    StudentProfile,
)
from app.tutor.subjects import meta as subject_meta

_rng = random.SystemRandom()
DIFF_ORDER = {"easy": 0, "medium": 1, "hard": 2, "unrated": 1}
MAX_PREREQ_PROBES = 2
OUTCOME_MESSAGES = {
    "improved": "Great work! You've shown you can do this skill.",
    "progressing": "You're improving. A bit more practice will make it solid.",
    "not_improved": "Let's practise a bit more with step-by-step questions.",
}


def _pick(cands: list[Item], target_rate: float = 0.6, k: int = 3) -> Item:
    ranked = sorted(cands, key=lambda i: abs((i.success_rate or 0.6) - target_rate))
    return _rng.choice(ranked[:k])


def _info(p: float) -> float:
    """Information a yes/no answer gives when success is predicted with probability p
    (largest at p = 0.5): the classic adaptive-testing criterion."""
    return p * (1 - p)


def _diagnostic_candidates(
    db: Session, user: User, asked_codes: set[str], skills: list[Skill]
) -> list[tuple[Skill, Item]]:
    """One representative unseen question per candidate skill: a rated medium question if
    possible (closest to 60% historical success), else any rated one. One query for all."""
    skills = [s for s in skills if s.code not in asked_codes]  # one question per standard
    if not skills:
        return []
    seen = engine.attempted_item_ids(db, user.id)
    by_skill: dict[int, list[Item]] = {}
    for i in db.scalars(engine.usable_items(db).where(Item.skill_id.in_([s.id for s in skills]))):
        if i.id not in seen and i.difficulty != "unrated":
            by_skill.setdefault(i.skill_id, []).append(i)
    out = []
    for s in skills:
        pool = by_skill.get(s.id)
        if not pool:
            continue
        medium = [i for i in pool if i.difficulty == "medium"] or pool
        out.append((s, _pick(medium)))
    return out


def start_grade(grade: int | None, grades: list[int]) -> int | None:
    """The grade the diagnostic starts at: one below the student's grade (at least 3), or
    the nearest available grade; the lowest grade when the student isn't sure."""
    if not grades:
        return None
    if grade is None:
        return min(grades)
    want = max(3, grade - 1)
    return min(grades, key=lambda g: (abs(g - want), g))


def choose_diagnostic_item(db: Session, user: User, a: Assessment) -> tuple[Item, dict]:
    """Adaptive diagnostic: pick the next question from what has been answered so far.

    1. If the last answer was wrong and that skill has a curated prerequisite that hasn't been
       checked, check the building block next (at most MAX_PREREQ_PROBES times).
    2. Otherwise cover the curriculum: only domains asked least so far are eligible, and among
       them the model picks the question it is LEAST sure about (predicted success closest to
       50%), which is the most informative one. Before any answer exists in the subject, the
       first question is a typical-difficulty question near the student's grade.
    The reason for every choice is stored (plain `how` + `technical`).
    """
    subject = db.get(Subject, a.subject_id)
    trace = list((a.result or {}).get("trace", []))
    asked = [db.get(Item, i) for i in a.planned_item_ids]
    asked_skills = [db.get(Skill, i.skill_id) for i in asked if i]
    asked_codes = {s.code for s in asked_skills}
    probes = sum(1 for t in trace if t.get("kind") == "prerequisite")
    plain = "This question helps us find your level."

    last = db.scalar(
        select(Interaction)
        .where(Interaction.assessment_id == a.id)
        .order_by(Interaction.created_at.desc(), Interaction.id.desc())
        .limit(1)
    )
    if last is not None and not last.is_correct and probes < MAX_PREREQ_PROBES:
        missed = db.get(Skill, last.skill_id)
        pre_skills = list(
            db.scalars(
                select(Skill)
                .join(SkillPrerequisite, SkillPrerequisite.prerequisite_id == Skill.id)
                .where(
                    SkillPrerequisite.skill_id == missed.id,
                    Skill.is_available,
                    Skill.subject_id == a.subject_id,
                )
                .order_by(Skill.grade, Skill.code)
            )
        )
        cands = _diagnostic_candidates(db, user, asked_codes, pre_skills)
        if cands:
            skill, item = cands[0]
            return item, {
                "kind": "prerequisite",
                "skill_id": skill.id,
                "skill": skill.name,
                "how": "A building block of the last question, to see where to start.",
                "reason": f"You missed the {missed.name} question, so MENTORX checks one of its "
                f"building blocks ({skill.code}) before moving on.",
            }

    core = list(
        db.scalars(
            select(Skill)
            .where(
                Skill.subject_id == a.subject_id,
                Skill.is_available,
                Skill.n_items >= subject_meta(subject.code)["core_min_items"],
            )
            .order_by(Skill.grade, Skill.code)
        )
    )
    cands = _diagnostic_candidates(db, user, asked_codes, core)
    if not cands:
        raise AppError(409, "no_content", "There are no more questions for this diagnostic.")
    per_domain: dict[str, int] = {}
    for s in asked_skills:
        per_domain[s.domain_code] = per_domain.get(s.domain_code, 0) + 1
    least = min(per_domain.get(s.domain_code, 0) for s, _ in cands)
    cands = [(s, i) for s, i in cands if per_domain.get(s.domain_code, 0) == least]

    h = kt.state_for(db, user.id, subject.id, subject.code)
    preds = kt.predict_items(h, [i for _, i in cands], code=subject.code)
    if preds and preds[0] is not None:
        ranked = sorted(zip(cands, preds, strict=True), key=lambda cp: -_info(cp[1]))
        (skill, item), p = _rng.choice(ranked[:2])
        return item, {
            "kind": "model",
            "skill_id": skill.id,
            "skill": skill.name,
            "predicted_p": p,
            "how": plain,
            "reason": f"The model was least sure how you'd do on {skill.domain_name} "
            f"(predicted success {round(100 * p)}%), so this question tells us the most.",
        }
    prof = db.get(StudentProfile, user.id)
    grades = sorted({s.grade for s, _ in cands if s.grade is not None})
    g = start_grade(prof.grade if prof else None, grades)
    first = [(s, i) for s, i in cands if s.grade == g] or cands
    skill, item = _rng.choice(first)
    level = f"grade-{g} " if g is not None else ""
    return item, {
        "kind": "start",
        "skill_id": skill.id,
        "skill": skill.name,
        "how": plain,
        "reason": f"A typical {level}question to start with "
        f"({round(100 * (item.success_rate or 0.6))}% of students got it right first time).",
    }


def plan_skill(
    db: Session, user_id: uuid.UUID, skill_id: int, n: int, fresh_only: bool
) -> list[int]:
    seen = engine.attempted_item_ids(db, user_id)
    pool = [
        i
        for i in db.scalars(engine.usable_items(db, skill_id))
        if i.id not in seen or not fresh_only
    ]
    rated = [i for i in pool if i.difficulty != "unrated"]
    _rng.shuffle(rated)
    unrated = [i for i in pool if i.difficulty == "unrated"]
    _rng.shuffle(unrated)
    # a spread of difficulties: mostly medium, at least one easy and one hard when available
    want = ["easy", "medium", "medium", "hard", "medium", "easy", "hard", "medium"] * 3
    picked: list[Item] = []
    for d in want:
        if len(picked) >= n:
            break
        nxt = next((i for i in rated if i.difficulty == d and i not in picked), None)
        if nxt:
            picked.append(nxt)
    for i in [*rated, *unrated]:  # top up if a level ran out (unrated questions last)
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


def available_skill(db: Session, skill_id: int | None) -> Skill:
    """A skill that can be served now: available and in an active subject."""
    skill = db.get(Skill, skill_id) if skill_id is not None else None
    if skill is None or not skill.is_available:
        raise AppError(404, "skill_not_found", "That skill isn't available.")
    subject = db.get(Subject, skill.subject_id)
    if subject is None or not subject.is_active:
        raise AppError(404, "skill_not_found", "That skill isn't available.")
    return skill


def start(db: Session, user: User, kind: str, skill_id: int | None) -> Assessment:
    cfg = get_settings()
    profile_service.require(db, user)
    active = db.scalar(
        select(Assessment)
        .where(Assessment.user_id == user.id, Assessment.status == "active")
        .with_for_update()
    )
    skill = None
    if kind != "diagnostic":
        skill = available_skill(db, skill_id)
        subject = db.get(Subject, skill.subject_id)
    else:
        subject = profile_service.current_subject(db, user)
    if active:
        if active.kind == kind and active.skill_id == skill_id and active.subject_id == subject.id:
            return active  # resume
        active.status = "abandoned"
        active.completed_at = engine.now()
    profile_service.enroll(db, user, subject)
    target_n = None
    if kind == "diagnostic":
        planned, target_n = [], cfg.diagnostic_length  # chosen one at a time (adaptive)
        n_core = db.scalar(
            select(func.count())
            .select_from(Skill)
            .where(
                Skill.subject_id == subject.id,
                Skill.is_available,
                Skill.n_items >= subject_meta(subject.code)["core_min_items"],
            )
        )
        if not n_core:
            raise AppError(409, "no_content", "There are no questions available yet.")
        target_n = min(target_n, int(n_core))
    elif kind == "skill_check":
        planned = plan_skill(db, user.id, skill.id, cfg.skill_check_length, fresh_only=True)
    else:
        planned = plan_skill(db, user.id, skill.id, cfg.reassessment_length, fresh_only=True)
        if len(planned) < state.CHECK_MIN_FRESH:
            raise AppError(
                409,
                "not_enough_fresh_questions",
                "You've already seen almost every question in this skill, so a fair reassessment "
                "isn't possible. Keep practising instead.",
            )
    if not planned and not target_n:
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
        subject_id=subject.id,
        kind=kind,
        skill_id=skill.id if skill else None,
        planned_item_ids=planned,
        target_n=target_n,
        result=snapshot,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def to_out(db: Session, a: Assessment) -> dict:
    skill = db.get(Skill, a.skill_id) if a.skill_id else None
    subject = db.get(Subject, a.subject_id)
    return {
        "id": a.id,
        "kind": a.kind,
        "status": a.status,
        "subject": {"code": subject.code, "name": subject.name} if subject else None,
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
    subject = db.get(Subject, a.subject_id)
    if a.current_item_id is None:
        if a.answered_count >= a.target_count:
            raise AppError(409, "assessment_complete", "No questions left.")
        if a.kind == "diagnostic":
            item, why = choose_diagnostic_item(db, user, a)
            a.planned_item_ids = [*a.planned_item_ids, item.id]  # new list: JSON change tracked
            result = dict(a.result or {})
            result["trace"] = [*result.get("trace", []), {"item_id": item.id, **why}]
            a.result = result
        else:
            done = set(
                db.scalars(select(Interaction.item_id).where(Interaction.assessment_id == a.id))
            )
            remaining = [i for i in a.planned_item_ids if i not in done]
            if not remaining:
                raise AppError(409, "assessment_complete", "No questions left.")
            item = db.get(Item, remaining[0])
        h = kt.state_for(db, user.id, subject.id, subject.code)
        a.current_item_id = item.id
        a.current_served_at = engine.now()
        a.current_predicted_p = kt.predict_items(h, [item], code=subject.code)[0]
        db.commit()
    item = db.get(Item, a.current_item_id)
    out = engine.public_item(db, item, a.answered_count + 1, a.target_count)
    if a.kind == "diagnostic":
        trace = (a.result or {}).get("trace", [])
        why = next((t for t in reversed(trace) if t.get("item_id") == item.id), None)
        out["selection"] = (
            {
                "how": why.get("how") or "This question helps us find your level.",
                "technical": why.get("reason"),
            }
            if why
            else None
        )
    else:
        out["selection"] = {
            "how": "A fresh question from this skill, from easier to harder.",
            "technical": None,
        }
    return out


def answer(db: Session, user: User, assessment_id: uuid.UUID, item_id: int, response: dict) -> dict:
    a = _own(db, user, assessment_id, lock=True)
    if a.status != "active":
        raise AppError(409, "assessment_closed", "This assessment has finished.")
    if not engine.is_current(db, a.current_item_id, item_id):
        raise AppError(409, "question_mismatch", "That isn't the question currently shown.")
    item = db.get(Item, a.current_item_id)
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
        state.refresh(db, user.id, a.subject_id)
    db.commit()
    return {
        "interaction_id": inter.id,
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
    states = state.refresh(db, user.id, a.subject_id, t)
    profile_service.require(db, user)
    subject = db.get(Subject, a.subject_id)
    result = dict(a.result or {})
    result.update(
        {
            "accuracy": a.correct_count / max(a.answered_count, 1),
            "correct": a.correct_count,
            "answered": a.answered_count,
        }
    )
    if a.kind == "diagnostic":
        profile_service.mark_diagnostic_done(db, user, subject, t)
        counts: dict[str, int] = {}
        for st in states.values():
            counts[st.status] = counts.get(st.status, 0) + 1
        result["status_counts"] = counts
        trigger = "diagnostic"
    elif a.kind == "skill_check":
        profile_service.mark_diagnostic_done(db, user, subject, t)
        trigger = "skill_check"
    else:
        result.update(_reassessment_outcome(db, user.id, a, states.get(a.skill_id), cfg))
        trigger = "reassessment"
    a.result = result
    recommend.generate(db, user.id, trigger, t, a.subject_id)
    return result


def initial_accuracy_rows(db: Session, user_id: uuid.UUID, a: Assessment) -> list[bool]:
    """The student's first (up to 5) single-skill answers in the skill before this check."""
    return list(
        db.execute(
            select(Interaction.is_correct)
            .where(
                Interaction.user_id == user_id,
                Interaction.skill_id == a.skill_id,
                Interaction.n_skills == 1,  # mixed answers are never per-skill evidence
                Interaction.created_at < a.started_at,
            )
            .order_by(Interaction.created_at, Interaction.id)
            .limit(5)
        )
        .scalars()
        .all()
    )


def _reassessment_outcome(
    db: Session, user_id: uuid.UUID, a: Assessment, st: SkillState | None, cfg
) -> dict:
    """Initial observed accuracy (first answers in the skill, before this reassessment) vs now."""
    before_rows = initial_accuracy_rows(db, user_id, a)
    initial = sum(before_rows) / len(before_rows) if before_rows else None
    recent = a.correct_count / max(a.answered_count, 1)
    passed = recent >= cfg.reassessment_pass
    if passed or (
        recent >= 0.7 and initial is not None and recent - initial >= cfg.improvement_margin
    ):
        outcome = "improved"
    elif initial is not None and recent - initial >= cfg.improvement_margin:
        outcome = "progressing"
    else:
        outcome = "not_improved"
    if st is not None:
        st.reassessed_accuracy = recent
        now = engine.now()
        was_completed = st.completed_at is not None
        was_due = bool(st.revision_due_at and st.revision_due_at <= now)
        if passed:
            if was_completed and was_due:
                st.revision_stage = (st.revision_stage or 0) + 1  # a successful review
            # an early (not-due) pass keeps the stage; a first completion starts at stage 0
            st.completed_at = st.completed_at or now
            st.revision_due_at = now + timedelta(days=state.review_interval(st.revision_stage))
            if st.mode_override == "foundation":
                st.mode_override = None  # the step-by-step period ends with a passed check
        else:
            if was_completed:
                st.completed_at = None  # no longer shown as completed
                st.revision_stage = 0
                st.revision_due_at = now + timedelta(days=1)
        if outcome == "not_improved":
            st.mode_override = "foundation"  # step-by-step until the next passed check
    before = (a.result or {}).get("before", {})
    return {
        "initial_accuracy": initial,
        "initial_attempts": len(before_rows),
        "reassessment_accuracy": recent,
        "outcome": outcome,
        "message": OUTCOME_MESSAGES[outcome],
        "predicted_before": before.get("predicted_p"),
        "predicted_after": st.predicted_p if st else None,
        "completed": bool(st and st.completed_at and passed),
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
