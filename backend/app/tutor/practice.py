"""Adaptive practice for one skill.

Difficulty rule (product brief, step 10), applied within easy <= level <= hard:
- two correct answers in a row at the current level -> one level harder;
- two incorrect answers in a row -> one level easier;
- mixed -> stay. The count restarts after every change.

Choosing the question: unused single-skill questions of the skill at the current level are
preferred; among them the model picks the one whose predicted success is closest to the
mode's target (foundation 0.80 ... advanced 0.50). Difficulty levels are historical
(training students' first-attempt success). When the ideal question doesn't exist, a
labelled fallback is used and the reason is shown to the student.
"""

from __future__ import annotations

import random
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import User
from app.tutor import engine, kt, recommend, resources, state
from app.tutor import profile as profile_service
from app.tutor.models import Interaction, Item, PracticeSession, Skill, SkillState

LEVELS = ["easy", "medium", "hard"]
_rng = random.SystemRandom()


def adjust(level: str, streak: list[int]) -> tuple[str, list[int], str | None]:
    """Apply the 2-up / 2-down rule. Returns (new level, new streak, change or None)."""
    i = LEVELS.index(level)
    if len(streak) >= 2 and streak[-2:] == [1, 1] and i < 2:
        return LEVELS[i + 1], [], "up"
    if len(streak) >= 2 and streak[-2:] == [0, 0] and i > 0:
        return LEVELS[i - 1], [], "down"
    return level, streak[-2:], None


def _own(db: Session, user: User, session_id: uuid.UUID, lock: bool = False) -> PracticeSession:
    stmt = select(PracticeSession).where(
        PracticeSession.id == session_id, PracticeSession.user_id == user.id
    )
    if lock:
        stmt = stmt.with_for_update()
    s = db.scalar(stmt)
    if s is None:
        raise AppError(404, "practice_not_found", "Practice session not found.")
    return s


def start(db: Session, user: User, skill_id: int, guided: bool) -> PracticeSession:
    profile_service.require(db, user)
    skill = db.get(Skill, skill_id)
    if skill is None or not skill.is_available:
        raise AppError(404, "skill_not_found", "That skill isn't available.")
    active = db.scalar(
        select(PracticeSession)
        .where(PracticeSession.user_id == user.id, PracticeSession.status == "active")
        .with_for_update()
    )
    if active:
        if active.skill_id == skill_id and active.guided == guided:
            return active
        active.status, active.ended_at = "abandoned", engine.now()
    st = db.get(SkillState, (user.id, skill_id))
    if st is None:
        state.refresh(db, user.id)
        st = db.get(SkillState, (user.id, skill_id))
    mode = state.effective_mode(st)
    if guided and mode in ("independent", "advanced"):
        mode = "guided"
    s = PracticeSession(
        user_id=user.id,
        skill_id=skill_id,
        mode=mode,
        guided=guided,
        difficulty=state.MODE_POLICY[mode]["start"],
        target_count=get_settings().tutor_practice_length,
        recent=[],
        current_selection={},
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _choose(db: Session, user: User, s: PracticeSession) -> tuple[Item, dict]:
    seen = engine.attempted_item_ids(db, user.id)
    pool = list(db.scalars(engine.usable_items(db, s.skill_id)))
    fresh = [i for i in pool if i.id not in seen]
    note = None
    cands = [i for i in fresh if i.difficulty == s.difficulty]
    served = s.difficulty
    if not cands:
        # nearest other level first, then unrated questions
        order = sorted(LEVELS, key=lambda lv: abs(LEVELS.index(lv) - LEVELS.index(s.difficulty)))[
            1:
        ]
        for lv in [*order, "unrated"]:
            cands = [i for i in fresh if i.difficulty == lv]
            if cands:
                served = lv
                note = f"No unused {s.difficulty} questions are left in this skill, so this one is {lv}."
                break
    if not cands:
        in_session = set(
            db.scalars(select(Interaction.item_id).where(Interaction.practice_id == s.id))
        )
        wrong_before = set(
            db.scalars(
                select(Interaction.item_id).where(
                    Interaction.user_id == user.id,
                    Interaction.skill_id == s.skill_id,
                    ~Interaction.is_correct,
                )
            )
        )
        cands = [i for i in pool if i.id in wrong_before and i.id not in in_session] or [
            i for i in pool if i.id not in in_session
        ]
        if not cands:
            raise AppError(
                409, "no_content", "You've answered every question in this skill. Great effort!"
            )
        served = "review"
        note = "You've answered every new question in this skill. This is one you've seen before, as review."
    target = state.MODE_POLICY[s.mode]["target_p"]
    h = kt.state_for(db, user.id)
    preds = kt.predict_items(h, cands)
    if preds and preds[0] is not None:
        ranked = sorted(zip(cands, preds, strict=True), key=lambda ip: abs(ip[1] - target))
        item, p = _rng.choice(ranked[:2])
        how = f"Chosen by the model: predicted success {round(100 * p)}%, close to the {round(100 * target)}% target for {s.mode} mode."
    else:
        item, p = _rng.choice(cands), None
        how = "Chosen at random from the matching questions (no model prediction available yet)."
    return item, {
        "requested": s.difficulty,
        "served": served,
        "predicted_p": p,
        "how": how,
        "fallback_note": note,
    }


def next_item(db: Session, user: User, session_id: uuid.UUID) -> dict:
    s = _own(db, user, session_id, lock=True)
    if s.status != "active":
        raise AppError(409, "practice_closed", "This practice session has ended.")
    if s.current_item_id is None:
        item, sel = _choose(db, user, s)
        s.current_item_id = item.id
        s.current_served_at = engine.now()
        s.current_predicted_p = sel["predicted_p"]
        s.current_hint_used = False
        s.current_selection = sel
        db.commit()
    item = db.get(Item, s.current_item_id)
    out = engine.public_item(db, item, s.answered_count + 1, s.target_count)
    sel = s.current_selection or {}
    out["selection"] = {k: sel.get(k) for k in ("requested", "served", "how", "fallback_note")}
    out["mode"] = s.mode
    out["hint_used"] = s.current_hint_used
    out["hints_available"] = True
    return out


def hint(db: Session, user: User, session_id: uuid.UUID) -> dict:
    s = _own(db, user, session_id, lock=True)
    if s.status != "active" or s.current_item_id is None:
        raise AppError(409, "no_question", "There's no question to give a hint for.")
    s.current_hint_used = True
    db.commit()
    return resources.hint_for(db, s.skill_id)


def _feedback(correct: bool, change: str | None, mode: str, revealed: bool) -> str:
    if revealed:
        return "That's okay. Read the answer, then try a similar question. Learning takes time."
    if correct and change == "up":
        return "You're improving! Two in a row, so the next question is a little harder."
    if correct:
        return (
            "Good job! You understood this concept."
            if mode in ("foundation", "guided")
            else "Correct. Well reasoned."
        )
    if change == "down":
        return "Not quite. Let's strengthen the basics with an easier question next."
    return "Not quite. Let's review the concept with another example."


def answer(
    db: Session,
    user: User,
    session_id: uuid.UUID,
    item_id: int,
    response: dict,
    reveal: bool = False,
) -> dict:
    s = _own(db, user, session_id, lock=True)
    if s.status != "active":
        raise AppError(409, "practice_closed", "This practice session has ended.")
    if s.current_item_id != item_id:
        raise AppError(409, "question_mismatch", "That isn't the question currently shown.")
    item = db.get(Item, item_id)
    inter = engine.record(
        db,
        user.id,
        item,
        response,
        context="practice",
        served_at=s.current_served_at,
        predicted_p=s.current_predicted_p,
        practice_id=s.id,
        hint_used=s.current_hint_used,
        saw_answer=reveal,
    )
    before_level = s.difficulty
    s.difficulty, s.recent, change = adjust(
        s.difficulty, [*(s.recent or []), int(inter.is_correct)]
    )
    s.answered_count += 1
    s.correct_count += int(inter.is_correct)
    s.current_item_id = s.current_served_at = s.current_predicted_p = None
    s.current_hint_used = False
    complete = s.answered_count >= s.target_count
    states = state.refresh(db, user.id)
    summary = None
    if complete:
        s.status, s.ended_at = "completed", engine.now()
        summary = _summary(db, user, s, states.get(s.skill_id))
        recommend.generate(db, user.id, "practice")
    db.commit()
    return {
        "correct": inter.is_correct,
        "hint_used": inter.hint_used,
        "revealed": reveal,
        "correct_answer": engine.reveal(item),
        "message": _feedback(inter.is_correct, change, s.mode, reveal),
        "difficulty_before": before_level,
        "difficulty_next": s.difficulty,
        "difficulty_change": change,
        "answered": s.answered_count,
        "total": s.target_count,
        "complete": complete,
        "summary": summary,
    }


def _summary(db: Session, user: User, s: PracticeSession, st: SkillState | None) -> dict:
    acc = s.correct_count / max(s.answered_count, 1)
    c, n = engine.skill_accuracy(db, user.id, s.skill_id)
    if acc >= 0.7 and n >= 5:
        nxt = {
            "action": "reassess",
            "label": "Take a short reassessment",
            "why": "Your practice is going well. A reassessment with new questions will confirm it.",
        }
    elif acc < 0.4:
        nxt = {
            "action": "foundation",
            "label": "Review the basics, then practise again",
            "why": "Learning takes time. Let's strengthen the basics before moving ahead.",
        }
    else:
        nxt = {
            "action": "practice",
            "label": "Practise a little more",
            "why": "You're getting there. Another short round should help.",
        }
    return {
        "accuracy": acc,
        "correct": s.correct_count,
        "answered": s.answered_count,
        "skill_accuracy": c / n if n else None,
        "skill_attempts": n,
        "predicted_p": st.predicted_p if st else None,
        "mode": st and state.effective_mode(st),
        "next": nxt,
    }


def end(db: Session, user: User, session_id: uuid.UUID) -> dict:
    s = _own(db, user, session_id, lock=True)
    summary = None
    if s.status == "active":
        s.status, s.ended_at = "completed" if s.answered_count else "abandoned", engine.now()
        s.current_item_id = None
        if s.answered_count:
            states = state.refresh(db, user.id)
            summary = _summary(db, user, s, states.get(s.skill_id))
            recommend.generate(db, user.id, "practice")
        db.commit()
    return {"status": s.status, "summary": summary}
