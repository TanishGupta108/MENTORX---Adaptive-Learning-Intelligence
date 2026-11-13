"""Adaptive practice: one skill, mixed problems, or a spaced review of skills that are due.

Difficulty rule (product brief, step 10), applied within easy <= level <= hard:
- two correct answers in a row at the current level -> one level harder;
- two incorrect answers in a row -> one level easier;
- mixed -> stay. The count restarts after every change.

Choosing the question: unused single-skill questions of the skill at the current level are
preferred; among them the model picks the one whose predicted success is closest to the
mode's target (foundation 0.80 ... advanced 0.50). Difficulty levels are historical
(training students' first-attempt success). When the ideal question doesn't exist, a
labelled fallback is used and the reason is shown to the student.

Session length follows the student's pace (6 more support / 8 balanced / 10 challenge). A
skill session stops early (`early_stop`) after >= 5 answers once the mastery rule holds and a
fresh check can be offered ("mastered"), as soon as the skill is completed by the mastery rule
because too few unseen questions are left for a fresh check ("completed", see state.py),
straight away after 3 wrong answers in a row at the easy level ("stuck"), or when no unused
question is left ("enough").

Mixed practice (kind="mixed") uses the subject's multi-skill questions, preferring those whose
skills the student has already worked on. Mixed answers never count as per-skill evidence.

Review (kind="review") interleaves 2 single-skill questions from each skill that is due for
review (most overdue first, at most 4 skills). Review is retrieval practice, so seen questions
may come back: unseen ones first, then ones last answered wrong, then the longest ago. A due
skill is reviewable when it has >= 2 usable questions (`reviewable`, the one rule used by
Home, the skill page, the review summary and start_review). Its answers are normal evidence. At the
end, per skill: both right -> the next, longer review interval; otherwise review again
tomorrow from the first interval.
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
from app.tutor import ai, engine, kt, recommend, resources, state
from app.tutor import profile as profile_service
from app.tutor.assess import available_skill
from app.tutor.models import Interaction, Item, PracticeSession, Skill, SkillState
from app.tutor.subjects import meta as subject_meta

LEVELS = ["easy", "medium", "hard"]
ARTICLE = {"easy": "an easy", "medium": "a medium", "hard": "a hard", "unrated": "a"}
PACE_LENGTH = {"more_support": 6, "challenge": 10}
REVIEW_PER_SKILL = 2
_rng = random.SystemRandom()

EARLY_STOP_MESSAGES = {
    "mastered": "You've got this one! Take the short check to confirm it.",
    "stuck": "This one is tricky right now. Let's look at the key idea and an example, then "
    "try again step by step.",
    "enough": "You've answered every new question in this skill. Great effort!",
    "completed": "You've got this one! Too few new questions are left for a separate check, so "
    "your practice counts: this skill is now completed.",
}


def adjust(level: str, streak: list[int]) -> tuple[str, list[int], str | None]:
    """Apply the 2-up / 2-down rule. Returns (new level, new streak, change or None)."""
    i = LEVELS.index(level)
    if len(streak) >= 2 and streak[-2:] == [1, 1] and i < 2:
        return LEVELS[i + 1], [], "up"
    if len(streak) >= 2 and streak[-2:] == [0, 0] and i > 0:
        return LEVELS[i - 1], [], "down"
    return level, streak[-2:], None


def practice_length(pace: str) -> int:
    return PACE_LENGTH.get(pace, get_settings().tutor_practice_length)


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


PACE_TO_MIXED_MODE = {"more_support": "guided", "balanced": "independent", "challenge": "advanced"}
MIXED_MIN_SKILLS = 2


def practised_skills(db: Session, user_id: uuid.UUID, subject_id: int | None = None) -> set[int]:
    stmt = select(Interaction.skill_id).where(
        Interaction.user_id == user_id, Interaction.n_skills == 1
    )
    if subject_id is not None:
        stmt = stmt.join(Skill, Skill.id == Interaction.skill_id).where(
            Skill.subject_id == subject_id
        )
    return set(db.scalars(stmt.distinct()))


def _close_active(db: Session, user: User) -> PracticeSession | None:
    return db.scalar(
        select(PracticeSession)
        .where(PracticeSession.user_id == user.id, PracticeSession.status == "active")
        .with_for_update()
    )


def _session_subject(db: Session, s: PracticeSession) -> Subject:
    if s.skill_id is not None:
        return db.get(Subject, db.get(Skill, s.skill_id).subject_id)
    return db.get(Subject, (s.plan or {}).get("subject_id")) or db.scalar(
        select(Subject).where(Subject.code == "MATH")
    )


def mixed_available(db: Session, user: User, subject: Subject) -> tuple[bool, int, int]:
    """(available, skills practised, mixed questions) for the subject."""
    if not subject_meta(subject.code)["mixed"]:
        return False, 0, 0
    practised = len(practised_skills(db, user.id, subject.id))
    n = int(
        db.scalar(
            select(func.count()).select_from(
                engine.usable_items(db, mixed=True, subject_id=subject.id).subquery()
            )
        )
        or 0
    )
    return practised >= MIXED_MIN_SKILLS and n > 0, practised, n


def start_mixed(db: Session, user: User) -> PracticeSession:
    prof = profile_service.require(db, user)
    subject = profile_service.current_subject(db, user)
    ok, practised, n = mixed_available(db, user, subject)
    if not subject_meta(subject.code)["mixed"] or not n:
        raise AppError(409, "no_content", "There are no mixed questions available yet.")
    if practised < MIXED_MIN_SKILLS:
        raise AppError(
            409,
            "mixed_locked",
            "Mixed practice opens once you've answered questions in at least two skills. "
            "Take the diagnostic first.",
        )
    active = _close_active(db, user)
    if active:
        if active.kind == "mixed" and (active.plan or {}).get("subject_id") == subject.id:
            return active
        active.status, active.ended_at = "abandoned", engine.now()
    mode = PACE_TO_MIXED_MODE.get(prof.pace_preference, "independent")
    s = PracticeSession(
        user_id=user.id,
        kind="mixed",
        skill_id=None,
        mode=mode,
        guided=False,
        difficulty=state.MODE_POLICY[mode]["start"],
        target_count=get_settings().mixed_practice_length,
        recent=[],
        current_selection={},
        plan={"subject_id": subject.id},
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def due_skills(db: Session, user: User, subject: Subject, now=None) -> list[SkillState]:
    """Skills due for review in the subject, most overdue first."""
    now = now or engine.now()
    return list(
        db.scalars(
            select(SkillState)
            .join(Skill, Skill.id == SkillState.skill_id)
            .where(
                SkillState.user_id == user.id,
                Skill.subject_id == subject.id,
                Skill.is_available,
                SkillState.revision_due_at.is_not(None),
                SkillState.revision_due_at <= now,
            )
            .order_by(SkillState.revision_due_at, Skill.id)
        )
    )


def reviewable(db: Session, due: list[SkillState]) -> list[SkillState]:
    """The due skills a review can serve (>= REVIEW_PER_SKILL usable questions, seen or not).
    The single eligibility rule for Home, the skill page, summaries and start_review."""
    if not due:
        return []
    counts = dict(
        db.execute(
            select(Item.skill_id, func.count())
            .where(
                Item.skill_id.in_([st.skill_id for st in due]),
                Item.n_skills == 1,
                Item.is_active,
                Item.exclusion_reason.is_(None),
            )
            .group_by(Item.skill_id)
        ).all()
    )
    return [st for st in due if counts.get(st.skill_id, 0) >= REVIEW_PER_SKILL]


def plan_review(db: Session, user: User, subject: Subject) -> dict | None:
    """Skills (max review_max_skills) and 2 questions each, interleaved: unseen questions
    first, then seen ones (last answered wrong first, then the longest ago)."""
    cfg = get_settings()
    due = reviewable(db, due_skills(db, user, subject))[: cfg.review_max_skills]
    if not due:
        return None
    ids = [st.skill_id for st in due]
    pools: dict[int, list[Item]] = {}
    for i in db.scalars(engine.usable_items(db).where(Item.skill_id.in_(ids))):
        pools.setdefault(i.skill_id, []).append(i)
    last: dict[int, tuple] = {}  # item -> (last answer correct, when)
    for iid, ok, at in db.execute(
        select(Interaction.item_id, Interaction.is_correct, Interaction.created_at)
        .where(Interaction.user_id == user.id, Interaction.skill_id.in_(ids))
        .order_by(Interaction.created_at, Interaction.id)
    ):
        last[iid] = (ok, at)
    order = {"medium": 0, "easy": 1, "hard": 2, "unrated": 3}
    chosen: list[tuple[int, list[int]]] = []
    for sid in ids:
        pool = pools.get(sid, [])
        fresh = sorted(
            (i for i in pool if i.id not in last),
            key=lambda i: (order.get(i.difficulty, 3), i.id),
        )[:4]
        _rng.shuffle(fresh)
        seen = sorted((i for i in pool if i.id in last), key=lambda i: last[i.id])
        picks = [*fresh, *seen][:REVIEW_PER_SKILL]
        chosen.append((sid, [i.id for i in picks]))
    if not chosen:
        return None
    items = [chosen[k][1][r] for r in range(REVIEW_PER_SKILL) for k in range(len(chosen))]
    return {"subject_id": subject.id, "skills": [c[0] for c in chosen], "items": items}


def start_review(db: Session, user: User) -> PracticeSession:
    prof = profile_service.require(db, user)
    subject = profile_service.current_subject(db, user)
    active = _close_active(db, user)
    if active and active.kind == "review" and (active.plan or {}).get("subject_id") == subject.id:
        return active
    plan = plan_review(db, user, subject)
    if plan is None:
        raise AppError(409, "nothing_due", "Nothing is due for review right now.")
    if active:
        active.status, active.ended_at = "abandoned", engine.now()
    mode = PACE_TO_MIXED_MODE.get(prof.pace_preference, "independent")
    s = PracticeSession(
        user_id=user.id,
        kind="review",
        skill_id=None,
        mode=mode,
        guided=False,
        difficulty="medium",
        target_count=len(plan["items"]),
        recent=[],
        current_selection={},
        plan=plan,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def start(
    db: Session, user: User, skill_id: int | None, guided: bool, kind: str = "skill"
) -> PracticeSession:
    if kind == "mixed":
        return start_mixed(db, user)
    if kind == "review":
        return start_review(db, user)
    prof = profile_service.require(db, user)
    skill = available_skill(db, skill_id)
    active = _close_active(db, user)
    if active:
        if active.kind == "skill" and active.skill_id == skill_id and active.guided == guided:
            return active
        active.status, active.ended_at = "abandoned", engine.now()
    st = db.get(SkillState, (user.id, skill_id))
    if st is None:
        state.refresh(db, user.id, skill.subject_id)
        st = db.get(SkillState, (user.id, skill_id))
    mode = state.effective_mode(st)
    if state.is_stuck(st.attempts, list(st.recent or []), st.mastered_at):
        mode = "foundation"  # a change of strategy: step by step for this session
    if guided and mode in ("independent", "advanced"):
        mode = "guided"
    s = PracticeSession(
        user_id=user.id,
        kind="skill",
        skill_id=skill_id,
        mode=mode,
        guided=guided,
        difficulty=state.MODE_POLICY[mode]["start"],
        target_count=practice_length(prof.pace_preference),
        recent=[],
        current_selection={},
        plan={"subject_id": skill.subject_id, "easy_wrong_streak": 0},
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _mixed_pool(db: Session, user: User, subject: Subject) -> tuple[list[Item], dict]:
    """Multi-skill questions, best first: those whose skills the student has practised most."""
    pool = list(db.scalars(engine.usable_items(db, mixed=True, subject_id=subject.id)))
    skills_of = engine.item_skills(db, [i.id for i in pool])
    tried = practised_skills(db, user.id, subject.id)

    def overlap(i: Item) -> int:
        return len(set(skills_of.get(i.id, [i.skill_id])) & tried)

    best = max((overlap(i) for i in pool), default=0)
    if best > 0:
        pool = [i for i in pool if overlap(i) == best]
    return pool, skills_of


def _plain_how(s: PracticeSession, served: str, note: str | None) -> str:
    if s.kind == "mixed":
        return "A problem that mixes skills you've practised."
    if note:
        return "This one is a little different, because the ideal question was used up."
    change = (s.current_selection or {}).get("last_change")
    if s.answered_count == 0:
        return f"We start with {ARTICLE.get(served, 'a')} question at your level."
    if change == "up":
        return (
            f"{ARTICLE.get(served, 'a').capitalize()} question, because your last two were right."
        )
    if change == "down":
        return "Easier this time, to build confidence."
    return f"Another {served} question at your current level."


def _choose(db: Session, user: User, s: PracticeSession) -> tuple[Item, dict]:
    subject = _session_subject(db, s)
    if s.kind == "review":
        done = set(db.scalars(select(Interaction.item_id).where(Interaction.practice_id == s.id)))
        remaining = [i for i in (s.plan or {}).get("items", []) if i not in done]
        if not remaining:
            raise AppError(409, "no_content", "This review is finished.")
        item = db.get(Item, remaining[0])
        skill = db.get(Skill, item.skill_id)
        h = kt.state_for(db, user.id, subject.id, subject.code)
        p = kt.predict_items(h, [item], code=subject.code)[0]
        return item, {
            "requested": item.difficulty,
            "served": item.difficulty,
            "predicted_p": p,
            "how": f"A quick review of {skill.name}, a skill you learned earlier.",
            "technical": "Spaced review: skills come back after 3, 7, 14, 30 and 60 days, "
            "mixed together.",
            "fallback_note": None,
        }
    seen = engine.attempted_item_ids(db, user.id)
    skills_of: dict[int, list[int]] = {}
    if s.kind == "mixed":
        pool, skills_of = _mixed_pool(db, user, subject)
    else:
        pool = list(db.scalars(engine.usable_items(db, s.skill_id)))
    fresh = [i for i in pool if i.id not in seen]
    scope = "mixed set" if s.kind == "mixed" else "skill"
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
                note = f"No unused {s.difficulty} questions are left in this {scope}, so this one is {lv}."
                break
    if not cands:
        in_session = set(
            db.scalars(select(Interaction.item_id).where(Interaction.practice_id == s.id))
        )
        wrong_before = set(
            db.scalars(
                select(Interaction.item_id).where(
                    Interaction.user_id == user.id,
                    Interaction.item_id.in_([i.id for i in pool]),
                    ~Interaction.is_correct,
                )
            )
        )
        cands = [i for i in pool if i.id in wrong_before and i.id not in in_session] or [
            i for i in pool if i.id not in in_session
        ]
        if not cands:
            raise AppError(
                409, "no_content", f"You've answered every question in this {scope}. Great effort!"
            )
        served = "review"
        note = f"You've answered every new question in this {scope}. This is one you've seen before, as review."
    target = state.MODE_POLICY[s.mode]["target_p"]
    h = kt.state_for(db, user.id, subject.id, subject.code)
    preds = kt.predict_items(h, cands, skills_of, code=subject.code)
    if preds and preds[0] is not None:
        ranked = sorted(zip(cands, preds, strict=True), key=lambda ip: abs(ip[1] - target))
        item, p = _rng.choice(ranked[:2])
        technical = (
            f"Chosen by the model: predicted success {round(100 * p)}%, close to the "
            f"{round(100 * target)}% target for {s.mode} mode."
        )
    else:
        item, p = _rng.choice(cands), None
        technical = "Chosen at random from the matching questions (no model prediction yet)."
    return item, {
        "requested": s.difficulty,
        "served": served,
        "predicted_p": p,
        "how": _plain_how(s, served, note),
        "technical": technical,
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
    out["selection"] = {
        k: sel.get(k) for k in ("requested", "served", "how", "technical", "fallback_note")
    }
    out["mode"] = s.mode
    out["hint_used"] = s.current_hint_used
    out["hints_available"] = True
    return out


def hint(db: Session, user: User, session_id: uuid.UUID, use_ai: bool = False) -> dict:
    """The skill's key idea, or (use_ai) an AI hint for this exact question. Either way the
    answer is recorded as "hint used". If the AI hint isn't available, or gave the answer
    away, the skill hint is returned with `ai_failed: true` so the student can try again."""
    s = _own(db, user, session_id, lock=True)
    if s.status != "active" or s.current_item_id is None:
        raise AppError(409, "no_question", "There's no question to give a hint for.")
    item = db.get(Item, s.current_item_id)
    s.current_hint_used = True
    db.commit()
    if use_ai:
        out = ai.hint(db, user, item)
        if out is not None:
            return {
                "kind": "ai",
                "text": out["content"],
                "source": "AI tutor",
                "label": out["label"],
                "ai_failed": False,
            }
        fallback = resources.hint_for(db, item.skill_id)
        return {
            **fallback,
            "ai_failed": True,
            "note": "The AI tutor couldn't give a safe hint for this question right now, "
            "so here is the key idea instead.",
        }
    return {**resources.hint_for(db, item.skill_id), "ai_failed": False}


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


def _fresh_left(db: Session, user: User, s: PracticeSession) -> int:
    seen = select(Interaction.item_id).where(Interaction.user_id == user.id)
    return int(
        db.scalar(
            select(func.count()).select_from(
                engine.usable_items(db, s.skill_id).where(Item.id.not_in(seen)).subquery()
            )
        )
        or 0
    )


def _early_stop(
    db: Session, user: User, s: PracticeSession, st: SkillState | None, correct: bool, level: str
) -> str | None:
    """Why a skill session should end now (or None). See the module doc."""
    if s.kind != "skill":
        return None
    cfg = get_settings()
    plan = dict(s.plan or {})
    streak = plan.get("easy_wrong_streak", 0)
    streak = streak + 1 if (not correct and level == "easy") else 0
    plan["easy_wrong_streak"] = streak
    s.plan = plan
    if streak >= 3:
        return "stuck"
    if (
        s.answered_count >= cfg.early_stop_min_answers
        and st is not None
        and state.mastery_met(list(st.recent or []), st.attempts, cfg)
        and s.answered_count < s.target_count
        and state.can_check(db, user.id, s.skill_id)  # the check it leads to can start
    ):
        return "mastered"
    if s.answered_count < s.target_count and _fresh_left(db, user, s) == 0:
        return "enough"
    return None


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
    if not engine.is_current(db, s.current_item_id, item_id):
        raise AppError(409, "question_mismatch", "That isn't the question currently shown.")
    item = db.get(Item, s.current_item_id)
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
    requested = (s.current_selection or {}).get("requested") or before_level
    if s.kind == "review":
        change = None
    else:
        s.difficulty, s.recent, change = adjust(
            s.difficulty, [*(s.recent or []), int(inter.is_correct)]
        )
    s.answered_count += 1
    s.correct_count += int(inter.is_correct)
    s.current_item_id = s.current_served_at = s.current_predicted_p = None
    s.current_hint_used = False
    s.current_selection = {"last_change": change}
    subject = _session_subject(db, s)
    prev = db.get(SkillState, (user.id, s.skill_id)) if s.skill_id else None
    was_completed = prev is not None and prev.completed_at is not None
    states = state.refresh(db, user.id, subject.id)
    st = states.get(s.skill_id) if s.skill_id else None
    stop = _early_stop(db, user, s, st, inter.is_correct, requested)
    if s.kind == "skill" and st is not None and st.completed_at and not was_completed:
        stop = "completed"  # completed by the mastery rule just now (see state.refresh)
    complete = s.answered_count >= s.target_count or stop is not None
    summary = None
    if complete:
        s.status, s.ended_at = "completed", engine.now()
        if s.kind == "review":
            _finish_review(db, user, s, states)
        summary = _summary(db, user, s, st, stop)
        recommend.generate(db, user.id, "practice", subject_id=subject.id)
    db.commit()
    return {
        "interaction_id": inter.id,
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
        "early_stop": {"reason": stop, "message": EARLY_STOP_MESSAGES[stop]} if stop else None,
        "summary": summary,
    }


def _finish_review(
    db: Session, user: User, s: PracticeSession, states: dict[int, SkillState]
) -> None:
    """Move each reviewed skill along the review schedule (see module doc)."""
    now = engine.now()
    rows = db.execute(
        select(Interaction.skill_id, Interaction.is_correct).where(Interaction.practice_id == s.id)
    ).all()
    by_skill: dict[int, list[bool]] = {}
    for sid, ok in rows:
        by_skill.setdefault(sid, []).append(ok)
    for sid in (s.plan or {}).get("skills", []):
        st = states.get(sid) or db.get(SkillState, (user.id, sid))
        answers_ = by_skill.get(sid, [])
        if st is None or not answers_:
            continue
        if len(answers_) >= REVIEW_PER_SKILL and all(answers_):
            st.revision_stage = (st.revision_stage or 0) + 1
            st.revision_due_at = now + timedelta(days=state.review_interval(st.revision_stage))
        else:
            st.revision_stage = 0
            st.revision_due_at = now + timedelta(days=1)


def mixed_accuracy(db: Session, user_id: uuid.UUID, subject_id: int | None = None) -> tuple:
    stmt = select(func.count(), func.count().filter(Interaction.is_correct)).where(
        Interaction.user_id == user_id, Interaction.n_skills > 1
    )
    if subject_id is not None:
        stmt = stmt.join(Item, Item.id == Interaction.item_id).where(Item.subject_id == subject_id)
    n, c = db.execute(stmt).one()
    return int(c), int(n)


def _summary(
    db: Session, user: User, s: PracticeSession, st: SkillState | None, stop: str | None = None
) -> dict:
    acc = s.correct_count / max(s.answered_count, 1)
    subject = _session_subject(db, s)
    base = {
        "accuracy": acc,
        "correct": s.correct_count,
        "answered": s.answered_count,
        "early_stop": {"reason": stop, "message": EARLY_STOP_MESSAGES[stop]} if stop else None,
    }
    if s.kind == "mixed":
        c, n = mixed_accuracy(db, user.id, subject.id)
        return {
            **base,
            "skill_accuracy": c / n if n else None,
            "skill_attempts": n,
            "predicted_p": None,
            "mode": s.mode,
            "mixed": True,
            "next": {
                "action": "mixed" if acc >= 0.5 else "practice",
                "label": "Another mixed round" if acc >= 0.5 else "Back to your focus skill",
                "why": "Mixing skills is how real problems look. You're handling it well."
                if acc >= 0.5
                else "Mixed problems are hard. Strengthening one skill at a time will help.",
            },
        }
    if s.kind == "review":
        more = bool(reviewable(db, due_skills(db, user, subject)))
        return {
            **base,
            "skill_accuracy": None,
            "skill_attempts": s.answered_count,
            "predicted_p": None,
            "mode": s.mode,
            "review": True,
            "next": {
                "action": "review" if more else "home",
                "label": "Review more skills" if more else "Back to Home",
                "why": "More skills are due for a quick review."
                if more
                else "Reviews done. They'll come back later, spaced out, so you keep them.",
            },
        }
    c, n = engine.skill_accuracy(db, user.id, s.skill_id)
    info = state.mastery_info(st)
    if stop == "stuck" or (st is not None and info["stuck"]):
        states = {
            x.skill_id: x
            for x in db.scalars(select(SkillState).where(SkillState.user_id == user.id))
        }
        skills = {
            k.id: k
            for k in db.scalars(
                select(Skill).where(Skill.subject_id == subject.id, Skill.is_available)
            )
        }
        pre = recommend.unmet_prerequisite(
            s.skill_id, recommend.prerequisite_map(db, set(skills)), states, skills
        )
        if pre is not None:
            nxt = {
                "action": "prerequisite",
                "skill_id": pre,
                "label": f"Practise {skills[pre].name}",
                "why": f"This one is tricky right now. Let's strengthen {skills[pre].name} first.",
            }
        else:
            nxt = {
                "action": "learn",
                "skill_id": s.skill_id,
                "label": "Read the key idea and worked example",
                "why": "Let's look at the worked example and try a few step-by-step questions.",
            }
    elif stop == "completed":
        nxt = {
            "action": "home",
            "skill_id": s.skill_id,
            "label": "Back to Home",
            "why": "Skill completed from your practice. It will come back for a short review "
            "later, so you keep it.",
        }
    elif (
        stop == "mastered" or (info["mastered"] and not (st and st.completed_at))
    ) and state.can_check(db, user.id, s.skill_id):
        nxt = {
            "action": "reassess",
            "skill_id": s.skill_id,
            "label": "Take the short check",
            "why": "Your practice is going well. A short check with new questions will confirm it.",
        }
    elif acc < 0.4:
        nxt = {
            "action": "foundation",
            "skill_id": s.skill_id,
            "label": "Review the basics, then practise again",
            "why": "Learning takes time. Let's strengthen the basics before moving ahead.",
        }
    else:
        nxt = {
            "action": "practice",
            "skill_id": s.skill_id,
            "label": "Practise a little more",
            "why": "You're getting there. Another short round should help.",
        }
    return {
        **base,
        "skill_accuracy": c / n if n else None,
        "skill_attempts": n,
        "predicted_p": st.predicted_p if st else None,
        "mode": st and state.effective_mode(st),
        "mastery": info,
        "next": nxt,
    }


def end(db: Session, user: User, session_id: uuid.UUID) -> dict:
    s = _own(db, user, session_id, lock=True)
    summary = None
    if s.status == "active":
        s.status, s.ended_at = "completed" if s.answered_count else "abandoned", engine.now()
        s.current_item_id = None
        if s.answered_count:
            subject = _session_subject(db, s)
            states = state.refresh(db, user.id, subject.id)
            if s.kind == "review":
                _finish_review(db, user, s, states)
            summary = _summary(db, user, s, states.get(s.skill_id) if s.skill_id else None)
            recommend.generate(db, user.id, "practice", subject_id=subject.id)
        db.commit()
    return {"status": s.status, "summary": summary}
