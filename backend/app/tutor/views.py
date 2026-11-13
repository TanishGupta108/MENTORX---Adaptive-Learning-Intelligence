"""Read models for the student screens: home, catalog, diagnosis report, skill page, dashboard,
learning path and analytics. Every view is for the student's CURRENT subject unless it is
addressed by a skill id. Observed performance and model predictions are always returned in
SEPARATE fields, and a prediction is null when the real model didn't produce one.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Subject, User
from app.tutor import engine, kt, localtime, practice, recommend, resources, state
from app.tutor import profile as profile_service
from app.tutor.assess import available_skill
from app.tutor.models import (
    Assessment,
    Interaction,
    Item,
    PracticeSession,
    Resource,
    ResourceCompletion,
    Skill,
    SkillPrerequisite,
    SkillState,
    StudentProfile,
)
from app.tutor.subjects import meta as subject_meta

# Plain words (frontend STATUS_META must match).
STATUS_LABEL = {
    "likely_strength": "Strong",
    "developing": "Getting there",
    "potential_weakness": "Needs practice",
    "needs_assessment": "Not tried yet",
}
MODE_LABEL = {
    "foundation": "Step by step",
    "guided": "Guided",
    "independent": "On my own",
    "advanced": "Challenge",
}


def _subject_out(s: Subject) -> dict:
    m = subject_meta(s.code)
    return {
        "code": s.code,
        "name": s.name,
        "description": s.description,
        "attribution": m["attribution"],
        "notice": m["notice"],
    }


def _states(db: Session, user: User, subject: Subject) -> dict[int, SkillState]:
    states = {
        s.skill_id: s
        for s in db.scalars(
            select(SkillState)
            .join(Skill, Skill.id == SkillState.skill_id)
            .where(SkillState.user_id == user.id, Skill.subject_id == subject.id)
        )
    }
    if not states and profile_service.get(db, user):
        states = state.refresh(db, user.id, subject.id)
        db.commit()
    return states


def _subject_skills(db: Session, subject: Subject) -> list[Skill]:
    return list(
        db.scalars(
            select(Skill)
            .where(Skill.subject_id == subject.id, Skill.is_available)
            .order_by(Skill.grade, Skill.code, Skill.id)
        )
    )


def skill_out(skill: Skill, st: SkillState | None, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    attempts = st.attempts if st else 0
    recent = (st.recent or [])[-state.RECENT_WINDOW :] if st else []
    mode = state.effective_mode(st) if st else "guided"
    return {
        "id": skill.id,
        "code": skill.code,
        "name": skill.name,
        "grade": skill.grade,
        "domain_code": skill.domain_code,
        "domain_name": skill.domain_name,
        "n_items": skill.n_items,
        "status": st.status if st else "needs_assessment",
        "status_label": STATUS_LABEL[st.status if st else "needs_assessment"],
        "evidence": st.evidence if st else "none",
        "attempts": attempts,
        "correct": st.correct if st else 0,
        "observed_accuracy": (st.correct / attempts) if attempts else None,
        "recent_accuracy": (sum(recent) / len(recent)) if recent else None,
        "hints_used": st.hints_used if st else 0,
        "predicted_p": st.predicted_p if st else None,
        "mode": mode,
        "mode_label": MODE_LABEL[mode],
        "mode_is_override": bool(st and st.mode_override),
        "completed": bool(st and st.completed_at),
        "reassessed_accuracy": st.reassessed_accuracy if st else None,
        "revision_due_at": st.revision_due_at if st else None,
        "review_due": bool(st and st.revision_due_at and st.revision_due_at <= now),
        "last_practiced_at": st.last_practiced_at if st else None,
        "mastery": state.mastery_info(st),
    }


def catalog(db: Session, user: User) -> dict:
    subject = profile_service.current_subject(db, user)
    states = _states(db, user, subject)
    skills = _subject_skills(db, subject)
    domains: dict[str, dict] = {}
    for s in skills:
        d = domains.setdefault(
            s.domain_code, {"code": s.domain_code, "name": s.domain_name, "skills": []}
        )
        d["skills"].append(skill_out(s, states.get(s.id)))
    return {
        "subject": _subject_out(subject),
        "n_skills": len(skills),
        "n_questions": sum(s.n_items for s in skills),
        "domains": sorted(domains.values(), key=lambda d: -len(d["skills"])),
        "model": kt.info(subject.code).__dict__,
    }


def _recs_out(
    db: Session,
    user: User,
    subject: Subject,
    states: dict[int, SkillState],
    limit: int | None = None,
) -> list[dict]:
    recs = recommend.current_fresh(db, user.id, subject.id)[:limit]
    skills = {
        s.id: s for s in db.scalars(select(Skill).where(Skill.id.in_([r.skill_id for r in recs])))
    }
    n_res = dict(
        db.execute(
            select(Resource.skill_id, func.count())
            .where(Resource.skill_id.in_(list(skills)), Resource.is_active)
            .group_by(Resource.skill_id)
        ).all()
    )
    return [
        {
            "priority": r.priority,
            "reason_code": r.reason_code,
            "reason": r.reason_text,
            "activities": r.activities,
            "resources_available": int(n_res.get(r.skill_id, 0)),
            "skill": skill_out(skills[r.skill_id], states.get(r.skill_id)),
        }
        for r in recs
        if r.skill_id in skills
    ]


def _latest_placement(db: Session, user: User, subject: Subject) -> Assessment | None:
    return db.scalar(
        select(Assessment)
        .where(
            Assessment.user_id == user.id,
            Assessment.subject_id == subject.id,
            Assessment.status == "completed",
            Assessment.kind.in_(("diagnostic", "skill_check")),
        )
        .order_by(Assessment.completed_at.desc())
        .limit(1)
    )


def diagnosis(db: Session, user: User) -> dict:
    subject = profile_service.current_subject(db, user)
    states = _states(db, user, subject)
    a = _latest_placement(db, user, subject)
    skills = {s.id: s for s in _subject_skills(db, subject)}
    assessed = [
        skill_out(skills[sid], st)
        for sid, st in states.items()
        if sid in skills and st.attempts > 0
    ]
    order = {"potential_weakness": 0, "developing": 1, "likely_strength": 2}
    assessed.sort(key=lambda s: (order.get(s["status"], 3), s["observed_accuracy"] or 0))
    unassessed = [
        skill_out(skills[sid], st)
        for sid, st in states.items()
        if sid in skills and st.attempts == 0
    ]
    with_pred = [s for s in unassessed if s["predicted_p"] is not None]
    weak = [s for s in assessed if s["status"] == "potential_weakness"]
    strong = [s for s in assessed if s["status"] == "likely_strength"]
    if weak:
        headline = f"{weak[0]['name']} needs more practice. Let's start there."
    elif strong:
        headline = f"You did well on {strong[0]['name']}. Let's build on that."
    else:
        headline = "We have a first picture of your skills. Practice will make it sharper."
    return {
        "subject": _subject_out(subject),
        "assessment": {
            "id": a.id,
            "kind": a.kind,
            "correct": a.correct_count,
            "answered": a.answered_count,
            "completed_at": a.completed_at,
        }
        if a
        else None,
        "headline": headline,
        "counts": {
            k: sum(1 for s in assessed + unassessed if s["status"] == k) for k in STATUS_LABEL
        },
        "assessed": assessed,
        "model_estimates_for_unassessed": sorted(with_pred, key=lambda s: s["predicted_p"])[:8],
        "recommendations": _recs_out(db, user, subject, states, 3),
        "selection_trace": _diagnostic_trace(db, a) if a and a.kind == "diagnostic" else [],
        "model": kt.info(subject.code).__dict__,
    }


def _diagnostic_trace(db: Session, a: Assessment) -> list[dict]:
    """Why each diagnostic question was chosen, with the observed result next to it."""
    results = dict(
        db.execute(
            select(Interaction.item_id, Interaction.is_correct).where(
                Interaction.assessment_id == a.id
            )
        ).all()
    )
    return [
        {
            "position": i + 1,
            "skill_id": t.get("skill_id"),
            "skill": t.get("skill"),
            "kind": t.get("kind"),
            "how": t.get("how"),
            "reason": t.get("reason"),
            "predicted_p": t.get("predicted_p"),
            "correct": results.get(t.get("item_id")),
        }
        for i, t in enumerate((a.result or {}).get("trace", []))
    ]


def _recent_mistakes(db: Session, user: User, skill_id: int, limit: int = 4) -> list[dict]:
    rows = db.execute(
        select(Interaction, Item)
        .join(Item, Item.id == Interaction.item_id)
        .where(
            Interaction.user_id == user.id,
            Interaction.skill_id == skill_id,
            Interaction.n_skills == 1,
            ~Interaction.is_correct,
        )
        .order_by(Interaction.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "interaction_id": inter.id,
            "item_id": engine.public_id(db, it),
            "body_html": it.body_html,
            "answer_type": it.answer_type,
            "options": it.options,
            "media": engine.public_media(it),
            "your_response": inter.response,
            "correct_answer": engine.reveal(it),
            "revealed": inter.saw_answer,
            "at": inter.created_at,
        }
        for inter, it in rows
    ]


def _last_reassessment(db: Session, user: User, skill_id: int) -> Assessment | None:
    return db.scalar(
        select(Assessment)
        .where(
            Assessment.user_id == user.id,
            Assessment.skill_id == skill_id,
            Assessment.kind == "reassessment",
            Assessment.status == "completed",
        )
        .order_by(Assessment.completed_at.desc())
        .limit(1)
    )


def next_activity_for(
    skill: Skill,
    st: SkillState | None,
    struggling: bool,
    unmet_prereq: Skill | None,
    now: datetime,
    can_review: bool = True,
    can_check: bool = True,
) -> dict:
    """The one primary action on a skill page (and in practice summaries). `can_review` /
    `can_check` come from practice.reviewable / state.can_check, the same rules the start
    endpoints apply, so the button never leads to a refusal."""
    if not st or st.attempts == 0:
        return {"action": "skill_check", "label": "Take a short skill check", "skill_id": skill.id}
    info = state.mastery_info(st)
    if info["stuck"]:
        if unmet_prereq is not None:
            return {
                "action": "prerequisite",
                "label": f"Practise {unmet_prereq.name} first",
                "skill_id": unmet_prereq.id,
            }
        return {"action": "learn", "label": "Read the key idea and example", "skill_id": skill.id}
    if st.revision_due_at and st.revision_due_at <= now and can_review:
        return {"action": "review", "label": "Quick review", "skill_id": skill.id}
    if info["mastered"] and not st.completed_at and can_check:
        return {"action": "reassess", "label": "Take the short check", "skill_id": skill.id}
    if struggling:
        return {
            "action": "foundation",
            "label": "Review the basics, then practise step by step",
            "skill_id": skill.id,
        }
    return {
        "action": "practice",
        "label": f"Continue {MODE_LABEL[state.effective_mode(st)]} practice",
        "skill_id": skill.id,
    }


def skill_detail(db: Session, user: User, skill_id: int) -> dict:
    now = datetime.now(UTC)
    skill = available_skill(db, skill_id)
    subject = db.get(Subject, skill.subject_id)
    states = _states(db, user, subject)
    st = states.get(skill_id)
    base = skill_out(skill, st, now)
    res = resources.for_skill(db, user, skill_id)
    prereq_rows = db.execute(
        select(Skill, SkillPrerequisite.source)
        .join(SkillPrerequisite, SkillPrerequisite.prerequisite_id == Skill.id)
        .where(SkillPrerequisite.skill_id == skill_id, Skill.is_available)
    ).all()
    dependents = list(
        db.scalars(
            select(Skill)
            .join(SkillPrerequisite, SkillPrerequisite.skill_id == Skill.id)
            .where(SkillPrerequisite.prerequisite_id == skill_id, Skill.is_available)
        )
    )
    last_re = _last_reassessment(db, user, skill_id)
    outcome = (last_re.result or {}).get("outcome") if last_re else None
    struggling = bool(st) and (
        outcome == "not_improved" or (st.status == "potential_weakness" and st.attempts >= 5)
    )
    unmet = sorted(
        (
            p
            for p, _ in prereq_rows
            if states.get(p.id) is None or states[p.id].status != "likely_strength"
        ),
        key=lambda p: (p.grade or 0, p.code),
    )
    support = None
    if struggling or base["mastery"]["stuck"]:
        weak_prereqs = [
            skill_out(p, states.get(p.id), now)
            for p, _ in prereq_rows
            if states.get(p.id) is None
            or states[p.id].status in ("potential_weakness", "needs_assessment", "developing")
        ]
        support = {
            "message": "Learning takes time. Let's strengthen the basics before moving ahead.",
            "steps": [
                "Look at your recent mistakes and compare them with the correct answers.",
                "Re-read the key idea in the notes.",
                "Work through the worked example step by step.",
                "Practise step by step: easier questions, with hints available.",
                "Take a fresh check when practice feels comfortable.",
            ],
            "prerequisites_to_check": weak_prereqs,
            "no_prerequisite_note": None
            if prereq_rows
            else "No building-block skill is linked to this one, so the plan focuses on "
            "step-by-step practice in the same skill.",
        }
    seen = engine.attempted_item_ids(db, user.id)  # once, not per question (audit L2)
    pool = list(db.scalars(select(Item.id).where(*_usable_where(skill_id))))
    cfg = get_settings()
    fresh = sum(1 for i in pool if i not in seen)
    due = bool(st and st.revision_due_at and st.revision_due_at <= now)
    nxt = next_activity_for(
        skill,
        st,
        struggling,
        unmet[0] if unmet else None,
        now,
        can_review=bool(due and practice.reviewable(db, [st])),
        can_check=fresh >= state.CHECK_MIN_FRESH,
    )
    m = subject_meta(subject.code)
    return {
        **base,
        "subject": {"code": subject.code, "name": subject.name},
        "attribution": m["attribution"] if subject.code != "MATH" else None,
        "notice": m["notice"],
        "description": skill.description,
        "standard_url": skill.standard_url,
        "difficulty_counts": dict(
            db.execute(
                select(Item.difficulty, func.count())
                .where(*_usable_where(skill_id))
                .group_by(Item.difficulty)
            ).all()
        ),
        "fresh_questions": fresh,
        "check_min_fresh": state.CHECK_MIN_FRESH,
        "resources": res,
        "resources_done": sum(1 for r in res if r["completed"]),
        "prerequisites": [
            {**skill_out(p, states.get(p.id), now), "source": src} for p, src in prereq_rows
        ],
        "leads_to": [skill_out(d, states.get(d.id), now) for d in dependents],
        "recent_mistakes": _recent_mistakes(db, user, skill_id),
        "last_reassessment": {
            "id": last_re.id,
            "result": last_re.result,
            "completed_at": last_re.completed_at,
        }
        if last_re
        else None,
        "support_plan": support,
        "next_activity": nxt,
        "mode_policy": state.MODE_POLICY[state.effective_mode(st) if st else "guided"],
        "reassessment_length": cfg.reassessment_length,
    }


def _usable_where(skill_id: int) -> tuple:
    return (
        Item.skill_id == skill_id,
        Item.n_skills == 1,
        Item.is_active,
        Item.exclusion_reason.is_(None),
    )


# ---------------------------------------------------------------- daily activity and streak


def _daily(db: Session, user: User, days: int, subject: Subject | None = None) -> list[dict]:
    tz = localtime.tz_of(user)
    today = localtime.today(user)
    first = today - timedelta(days=days - 1)
    stmt = select(Interaction.created_at, Interaction.is_correct).where(
        Interaction.user_id == user.id,
        Interaction.created_at >= localtime.day_start(user, first),
    )
    if subject is not None:
        stmt = stmt.join(Item, Item.id == Interaction.item_id).where(Item.subject_id == subject.id)
    agg: dict[date, list[int]] = defaultdict(lambda: [0, 0])
    for ts, ok in db.execute(stmt).all():
        d = localtime.local_date(ts, tz)
        agg[d][0] += 1
        agg[d][1] += int(ok)
    out = []
    for i in range(days):
        d = first + timedelta(days=i)
        n, c = agg.get(d, [0, 0])
        out.append(
            {"date": d.isoformat(), "attempts": n, "correct": c, "accuracy": c / n if n else None}
        )
    return out


def streak(db: Session, user: User, daily_goal: int) -> dict:
    """Days in a row with at least one answer (in the student's timezone, every subject), and
    today's count vs the goal. A streak stays alive until the end of the next day."""
    tz = localtime.tz_of(user)
    since = datetime.now(UTC) - timedelta(days=400)
    stamps = db.scalars(
        select(Interaction.created_at).where(
            Interaction.user_id == user.id, Interaction.created_at >= since
        )
    ).all()
    local = [localtime.local_date(t, tz) for t in stamps]
    days = set(local)
    today = localtime.today(user)
    today_count = sum(1 for d in local if d == today)
    cur, d = 0, today if today in days else today - timedelta(days=1)
    while d in days:
        cur += 1
        d -= timedelta(days=1)
    longest, run, prev = 0, 0, None
    for day in sorted(days):
        run = run + 1 if prev is not None and (day - prev).days == 1 else 1
        longest, prev = max(longest, run), day
    return {
        "current": cur,
        "longest": longest,
        "today": today_count,
        "daily_goal": daily_goal,
        "goal_met": today_count >= daily_goal,
        "active_today": today in days,
    }


def _activity(db: Session, user: User, limit: int = 8, subject: Subject | None = None) -> list:
    items: list[dict] = []
    a_stmt = select(Assessment).where(Assessment.user_id == user.id)
    if subject is not None:
        a_stmt = a_stmt.where(Assessment.subject_id == subject.id)
    skill_names = (
        {s.id: s.name for s in db.scalars(select(Skill).where(Skill.subject_id == subject.id))}
        if subject is not None
        else {s.id: s.name for s in db.scalars(select(Skill))}
    )
    for a in db.scalars(a_stmt.order_by(Assessment.started_at.desc()).limit(limit)):
        name = skill_names.get(a.skill_id) if a.skill_id else None
        items.append(
            {
                "kind": a.kind,
                "title": {
                    "diagnostic": "Placement check",
                    "skill_check": "Skill check",
                    "reassessment": "Check",
                }[a.kind]
                + (f": {name}" if name else ""),
                "detail": f"{a.correct_count}/{a.answered_count} correct"
                + ("" if a.status == "completed" else f" ({a.status})"),
                "at": a.completed_at or a.started_at,
                "id": str(a.id),
                "skill_id": a.skill_id,
            }
        )
    for p in db.scalars(
        select(PracticeSession)
        .where(PracticeSession.user_id == user.id)
        .order_by(PracticeSession.started_at.desc())
        .limit(limit * 2)
    ):
        if subject is not None and _session_subject_id(p, skill_names) not in (subject.id, None):
            continue
        if p.kind == "skill" and p.skill_id not in skill_names:
            continue
        title = {
            "mixed": "Mixed practice",
            "review": "Review",
        }.get(
            p.kind
        ) or f"{'Guided practice' if p.guided else 'Practice'}: {skill_names[p.skill_id]}"
        items.append(
            {
                "kind": "practice",
                "title": title,
                "detail": f"{p.correct_count}/{p.answered_count} correct",
                "at": p.ended_at or p.started_at,
                "id": str(p.id),
                "skill_id": p.skill_id,
            }
        )
    rows = db.execute(
        select(ResourceCompletion, Resource)
        .join(Resource, Resource.id == ResourceCompletion.resource_id)
        .where(ResourceCompletion.user_id == user.id)
        .order_by(ResourceCompletion.completed_at.desc())
        .limit(limit)
    ).all()
    for rc, r in rows:
        if subject is not None and r.skill_id not in skill_names:
            continue
        items.append(
            {
                "kind": "resource",
                "title": f"Completed: {r.title}",
                "detail": r.kind.replace("_", " "),
                "at": rc.completed_at,
                "id": str(r.id),
                "skill_id": r.skill_id,
            }
        )
    items.sort(key=lambda x: x["at"], reverse=True)
    return items[:limit]


def _session_subject_id(p: PracticeSession, skill_names: dict[int, str]) -> int | None:
    if p.skill_id is not None:
        return None  # checked via skill_names
    return (p.plan or {}).get("subject_id")


def _mixed_info(db: Session, user: User, subject: Subject, states: dict) -> dict:
    practised = sum(1 for st in states.values() if st.attempts > 0)
    if not subject_meta(subject.code)["mixed"]:
        return {
            "available": False,
            "skills_practised": practised,
            "needs_skills": practice.MIXED_MIN_SKILLS,
            "questions": 0,
            "answered": 0,
            "accuracy": None,
        }
    left_q = select(func.count()).select_from(
        engine.usable_items(db, mixed=True, subject_id=subject.id).subquery()
    )
    mixed_left, mn, mc = db.execute(  # one statement for the pool size and the student's record
        select(
            left_q.scalar_subquery(),
            func.count(Interaction.id),
            func.count(Interaction.id).filter(Interaction.is_correct),
        )
        .select_from(Interaction)
        .join(Item, Item.id == Interaction.item_id)
        .where(
            Interaction.user_id == user.id,
            Interaction.n_skills > 1,
            Item.subject_id == subject.id,
        )
    ).one()
    mn, mc = int(mn or 0), int(mc or 0)
    return {
        "available": practised >= practice.MIXED_MIN_SKILLS and bool(mixed_left),
        "skills_practised": practised,
        "needs_skills": practice.MIXED_MIN_SKILLS,
        "questions": int(mixed_left or 0),
        "answered": mn,
        "accuracy": mc / mn if mn else None,
    }


def dashboard(db: Session, user: User) -> dict:
    prof = profile_service.require(db, user)
    subject = profile_service.current_subject(db, user)
    states = _states(db, user, subject)
    skills = {s.id: s for s in _subject_skills(db, subject)}
    assessed = [st for sid, st in states.items() if sid in skills and st.attempts > 0]
    recs = _recs_out(db, user, subject, states, 4)
    week = datetime.now(UTC) - timedelta(days=7)
    sessions_done = db.scalar(
        select(func.count())
        .select_from(PracticeSession)
        .where(PracticeSession.user_id == user.id, PracticeSession.status == "completed")
    )
    q_week = db.scalar(
        select(func.count())
        .select_from(Interaction)
        .where(Interaction.user_id == user.id, Interaction.created_at >= week)
    )
    by_status: dict[str, list[dict]] = {k: [] for k in STATUS_LABEL}
    for st in assessed:
        by_status[st.status].append(skill_out(skills[st.skill_id], st))
    due = [
        skill_out(skills[st.skill_id], st)
        for st in assessed
        if st.revision_due_at and st.revision_due_at <= datetime.now(UTC)
    ]
    goal = profile_service.goal_progress(db, user)
    db.commit()  # goal achievement timestamp
    return {
        "name": user.full_name.split(" ")[0],
        "subject": {"code": subject.code, "name": subject.name},
        "diagnostic_completed": profile_service.diagnostic_done(db, user, subject),
        "goal_type": prof.goal_type,
        "continue": recs[0] if recs else None,
        "overview": {
            "skills_assessed": len(assessed),
            "likely_strengths": len(by_status["likely_strength"]),
            "needs_improvement": len(by_status["potential_weakness"])
            + len(by_status["developing"]),
            "practice_sessions": int(sessions_done or 0),
            "questions_this_week": int(q_week or 0),
            "skills_available": len(skills),
        },
        "recommendations": recs,
        "skill_map": {
            k: sorted(v, key=lambda s: s["code"])
            for k, v in by_status.items()
            if k != "needs_assessment"
        },
        "unassessed_count": len(skills) - len(assessed),
        "revision_due": due,
        "progress": _daily(db, user, 14, subject),
        "activity": _activity(db, user, 6, subject),
        "goal": goal,
        "streak": streak(db, user, prof.daily_goal),
        "mixed": _mixed_info(db, user, subject, states),
        "model": kt.info(subject.code).__dict__,
    }


def learning_path(db: Session, user: User) -> dict:
    profile_service.require(db, user)
    subject = profile_service.current_subject(db, user)
    states = _states(db, user, subject)
    skills = {s.id: s for s in _subject_skills(db, subject)}
    recs = recommend.current_fresh(db, user.id, subject.id)
    done_by_skill: dict[int, int] = defaultdict(int)
    total_by_skill: dict[int, int] = defaultdict(int)
    done = resources.completed_ids(db, user)
    for r in db.scalars(
        select(Resource).where(
            Resource.is_active, Resource.kind != "standard", Resource.skill_id.in_(list(skills))
        )
    ):
        total_by_skill[r.skill_id] += 1
        done_by_skill[r.skill_id] += int(r.id in done)

    def step(sid: int, label: str, reason: str | None, activities: list[str] | None) -> dict:
        st = states.get(sid)
        return {
            "skill": skill_out(skills[sid], st),
            "path_status": label,
            "reason": reason,
            "next_activity": (activities or [None])[0],
            "resources_done": done_by_skill[sid],
            "resources_total": total_by_skill[sid],
        }

    steps, seen = [], set()
    for i, r in enumerate(recs):
        if r.skill_id in skills:
            seen.add(r.skill_id)
            st = states.get(r.skill_id)
            label = (
                "Current Focus" if i == 0 else STATUS_LABEL[st.status if st else "needs_assessment"]
            )
            steps.append(step(r.skill_id, label, r.reason_text, r.activities))
    completed = [
        step(
            sid,
            "Completed",
            f"Check {round(100 * (st.reassessed_accuracy or 0))}% correct",
            ["Review when it's due"],
        )
        for sid, st in states.items()
        if sid in skills and st.completed_at and sid not in seen
    ]
    return {"steps": steps, "completed": completed}


def analytics(db: Session, user: User) -> dict:
    prof = profile_service.require(db, user)
    subject = profile_service.current_subject(db, user)
    states = _states(db, user, subject)
    skills = {s.id: s for s in db.scalars(select(Skill).where(Skill.subject_id == subject.id))}
    rows = db.execute(
        select(Interaction.context, Interaction.is_correct, Interaction.hint_used)
        .join(Item, Item.id == Interaction.item_id)
        .where(Interaction.user_id == user.id, Item.subject_id == subject.id)
    ).all()
    n = len(rows)
    by_ctx: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    hints = 0
    for ctx, ok, h in rows:
        by_ctx[ctx][0] += 1
        by_ctx[ctx][1] += int(ok)
        hints += int(h)
    skill_rows = [
        skill_out(skills[sid], st)
        for sid, st in states.items()
        if st.attempts > 0 and sid in skills
    ]
    skill_rows.sort(key=lambda s: -s["attempts"])
    assessments = db.scalars(
        select(Assessment)
        .where(
            Assessment.user_id == user.id,
            Assessment.status == "completed",
            Assessment.subject_id == subject.id,
        )
        .order_by(Assessment.completed_at)
    ).all()
    sessions = [
        p
        for p in db.scalars(
            select(PracticeSession)
            .where(PracticeSession.user_id == user.id, PracticeSession.answered_count > 0)
            .order_by(PracticeSession.started_at)
        )
        if (p.skill_id in skills) or (p.skill_id is None and _plan_subject(p) == subject.id)
    ]
    res_done = db.scalar(
        select(func.count())
        .select_from(ResourceCompletion)
        .join(Resource, Resource.id == ResourceCompletion.resource_id)
        .where(ResourceCompletion.user_id == user.id, Resource.skill_id.in_(list(skills)))
    )
    res_total = db.scalar(
        select(func.count())
        .select_from(Resource)
        .where(Resource.is_active, Resource.kind != "standard", Resource.skill_id.in_(list(skills)))
    )
    mastered = sum(
        1 for st in states.values() if st.completed_at or state.mastery_info(st)["mastered"]
    )
    goal = profile_service.goal_progress(db, user)
    db.commit()
    return {
        "subject": {"code": subject.code, "name": subject.name},
        "totals": {
            "questions": n,
            "correct": sum(c for _, c in by_ctx.values()),
            "observed_accuracy": (sum(c for _, c in by_ctx.values()) / n) if n else None,
            "assessment_accuracy": (by_ctx["assessment"][1] / by_ctx["assessment"][0])
            if by_ctx["assessment"][0]
            else None,
            "practice_accuracy": (by_ctx["practice"][1] / by_ctx["practice"][0])
            if by_ctx["practice"][0]
            else None,
            "hint_rate": hints / n if n else None,
            "mixed_accuracy": (lambda c, m: c / m if m else None)(
                *practice.mixed_accuracy(db, user.id, subject.id)
            ),
            "assessments": len(assessments),
            "practice_sessions": len(sessions),
            "resources_completed": int(res_done or 0),
            "resources_total": int(res_total or 0),
            "skills_mastered": mastered,
        },
        "goal": goal,
        "streak": streak(db, user, prof.daily_goal),
        "daily": _daily(db, user, 30, subject),
        "skills": skill_rows,
        "assessments": [
            {
                "id": a.id,
                "kind": a.kind,
                "skill": skills[a.skill_id].name if a.skill_id in skills else None,
                "accuracy": a.correct_count / max(a.answered_count, 1),
                "correct": a.correct_count,
                "answered": a.answered_count,
                "completed_at": a.completed_at,
                "outcome": (a.result or {}).get("outcome"),
            }
            for a in assessments
        ],
        "practice": [
            {
                "id": p.id,
                "skill": skills[p.skill_id].name
                if p.skill_id in skills
                else ("Review" if p.kind == "review" else "Mixed practice"),
                "kind": p.kind,
                "mode": p.mode,
                "accuracy": p.correct_count / max(p.answered_count, 1),
                "answered": p.answered_count,
                "started_at": p.started_at,
            }
            for p in sessions
        ],
        "activity": _activity(db, user, 12, subject),
        "model": kt.info(subject.code).__dict__,
    }


def _plan_subject(p: PracticeSession) -> int | None:
    sid = (p.plan or {}).get("subject_id")
    return sid if sid is not None else None


# ---------------------------------------------------------------- home (GET /home)


def _action(
    kind: str,
    skill: Skill | None,
    title: str,
    reason: str,
    progress_hint: str | None,
    start: dict,
) -> dict:
    return {
        "kind": kind,
        "skill": {"id": skill.id, "name": skill.name, "code": skill.code} if skill else None,
        "title": title,
        "reason": reason,
        "progress_hint": progress_hint,
        "start": start,
    }


def _rec_action(
    r,
    skill: Skill,
    st: SkillState | None,
    skills: dict[int, Skill],
    states: dict[int, SkillState],
    prereqs: dict[int, list[int]],
    learned: set[int],
    checkable: set[int] | None = None,
) -> dict:
    """Map one recommendation to a NextAction (spec C2). A check is offered only for skills in
    `checkable` (state.can_check), as assess.start would refuse the others."""
    info = state.mastery_info(st)
    hint = info["progress_hint"]
    if r.reason_code == "stuck":
        pre = recommend.unmet_prerequisite(skill.id, prereqs, states, skills)
        if pre is not None:
            p = skills[pre]
            return _action(
                "prerequisite",
                p,
                p.name,
                r.reason_text,
                state.mastery_info(states.get(pre))["progress_hint"],
                {"endpoint": "practice", "skill_id": p.id, "guided": True},
            )
        return _action(
            "learn",
            skill,
            skill.name,
            r.reason_text,
            hint,
            {"endpoint": "learn", "skill_id": skill.id},
        )
    if st is None or st.attempts == 0:
        return _action(
            "skill_check",
            skill,
            skill.name,
            r.reason_text,
            None,
            {"endpoint": "assessment", "kind": "skill_check", "skill_id": skill.id},
        )
    if info["mastered"] and not st.completed_at and skill.id in (checkable or set()):
        return _action(
            "reassess",
            skill,
            skill.name,
            "You've mastered this in practice. A short check with new questions confirms it.",
            hint,
            {"endpoint": "assessment", "kind": "reassessment", "skill_id": skill.id},
        )
    mode = state.effective_mode(st)
    if mode == "foundation" and skill.id not in learned:
        return _action(
            "learn",
            skill,
            skill.name,
            r.reason_text,
            hint,
            {"endpoint": "learn", "skill_id": skill.id},
        )
    return _action(
        "practice",
        skill,
        skill.name,
        r.reason_text,
        hint,
        {"endpoint": "practice", "skill_id": skill.id, "guided": mode in ("foundation", "guided")},
    )


def _pace_suggestion(db: Session, user: User, prof: StudentProfile) -> dict | None:
    cfg = get_settings()
    if prof.pace_suggestion_dismissed_at and prof.pace_suggestion_dismissed_at > datetime.now(
        UTC
    ) - timedelta(days=cfg.pace_dismiss_days):
        return None
    rows = db.execute(
        select(
            Interaction.is_correct,
            Interaction.hint_used,
            Interaction.saw_answer,
            func.coalesce(Interaction.practice_id, Interaction.assessment_id),
        )
        .where(Interaction.user_id == user.id, Interaction.n_skills == 1)
        .order_by(Interaction.created_at.desc(), Interaction.id.desc())
        .limit(cfg.pace_window)
    ).all()
    rows = [(c, h, s, str(k)) for c, h, s, k in reversed(rows)]
    suggested = state.pace_suggestion(rows, prof.pace_preference, cfg)
    if suggested is None:
        return None
    return {"suggested": suggested, "message": state.PACE_MESSAGES[suggested]}


def home(db: Session, user: User) -> dict:
    """Everything the Home screen needs, in one call (<= 15 SQL statements)."""
    cfg = get_settings()
    now = datetime.now(UTC)
    prof = profile_service.require(db, user)
    subject = profile_service.current_subject(db, user)
    diag_done = profile_service.diagnostic_done(db, user, subject)
    states = _states(db, user, subject)
    skills = {s.id: s for s in _subject_skills(db, subject)}

    # resume: the active practice session / assessment in this subject
    last_session = db.scalar(
        select(PracticeSession)
        .where(PracticeSession.user_id == user.id)
        .order_by(PracticeSession.started_at.desc())
        .limit(1)
    )
    # the active check and the latest placement check, in one statement
    subject_assessments = list(
        db.scalars(
            select(Assessment)
            .where(
                Assessment.user_id == user.id,
                Assessment.subject_id == subject.id,
                (Assessment.status == "active")
                | (
                    (Assessment.status == "completed")
                    & Assessment.kind.in_(("diagnostic", "skill_check"))
                ),
            )
            .order_by(Assessment.started_at.desc())
        )
    )
    active_a = next((x for x in subject_assessments if x.status == "active"), None)
    resume = None
    if active_a is not None:
        sk = skills.get(active_a.skill_id) if active_a.skill_id else None
        title = {
            "diagnostic": "Finish your placement check",
            "skill_check": "Finish your skill check",
            "reassessment": "Finish your check",
        }[active_a.kind]
        resume = _action(
            "resume",
            sk,
            title,
            "You have an unfinished check. Pick up where you left off.",
            f"{active_a.answered_count} of {active_a.target_count} answered",
            {"endpoint": "resume_assessment", "assessment_id": str(active_a.id)},
        )
    elif last_session is not None and last_session.status == "active":
        in_subject = (
            last_session.skill_id in skills
            if last_session.skill_id is not None
            else (last_session.plan or {}).get("subject_id", subject.id) == subject.id
        )
        if in_subject:
            sk = skills.get(last_session.skill_id) if last_session.skill_id else None
            title = (
                f"Continue practising {sk.name}"
                if sk
                else {"mixed": "Continue mixed practice", "review": "Continue your review"}.get(
                    last_session.kind, "Continue practice"
                )
            )
            resume = _action(
                "resume",
                sk,
                title,
                "You have an unfinished practice session. Pick up where you left off.",
                f"{last_session.answered_count} of {last_session.target_count} answered",
                {"endpoint": "resume_practice", "session_id": str(last_session.id)},
            )

    due = practice.reviewable(  # the same rule start_review uses
        db,
        sorted(
            (
                st
                for sid, st in states.items()
                if sid in skills and st.revision_due_at and st.revision_due_at <= now
            ),
            key=lambda st: (st.revision_due_at, st.skill_id),
        ),
    )
    reviews_due = {
        "count": len(due),
        "skills": [{"id": st.skill_id, "name": skills[st.skill_id].name} for st in due[:5]],
    }

    actions: list[dict] = []
    if resume is not None:
        actions.append(resume)
    if not diag_done and skills:
        actions.append(
            _action(
                "diagnostic",
                None,
                f"Start your {subject.name} placement check",
                "A short placement check shows where to start, so practice fits you.",
                f"{cfg.diagnostic_length} short questions",
                {"endpoint": "assessment", "kind": "diagnostic", "skill_id": None},
            )
        )
    if due:
        actions.append(
            _action(
                "review",
                None,
                "Quick review",
                "Reviewing skills at spaced times helps you remember them.",
                f"{len(due)} skill{'s' if len(due) != 1 else ''} due",
                {"endpoint": "review"},
            )
        )
    if diag_done:
        prereqs = recommend.prerequisite_map(db, set(skills))
        learned = set(
            db.scalars(
                select(Resource.skill_id)
                .join(ResourceCompletion, ResourceCompletion.resource_id == Resource.id)
                .where(ResourceCompletion.user_id == user.id)
            )
        )
        stuck_first = []
        recs = [
            r
            for r in recommend.current_fresh(db, user.id, subject.id, now)
            if r.skill_id in skills and r.reason_code != "review"
        ]
        mastered = [
            r.skill_id
            for r in recs
            if (st := states.get(r.skill_id)) is not None
            and not st.completed_at
            and state.mastery_info(st)["mastered"]
        ]
        checkable = {
            sid
            for sid, n in state.fresh_counts(db, user.id, mastered).items()
            if n >= state.CHECK_MIN_FRESH
        }
        for r in recs:
            a = _rec_action(
                r,
                skills[r.skill_id],
                states.get(r.skill_id),
                skills,
                states,
                prereqs,
                learned,
                checkable,
            )
            (stuck_first if a["kind"] == "prerequisite" else actions).append(a)
        # a stuck skill with an unmet building block comes before the other recommendations
        insert_at = next(
            (
                i
                for i, a in enumerate(actions)
                if a["kind"] not in ("resume", "diagnostic", "review")
            ),
            len(actions),
        )
        actions[insert_at:insert_at] = stuck_first

    unique: list[dict] = []
    keys: set[tuple] = set()
    for a in actions:
        k = (a["kind"], a["skill"]["id"] if a["skill"] else None, str(a["start"]))
        if k not in keys:
            keys.add(k)
            unique.append(a)
    nxt = unique[0] if unique else None
    up_next = [a for a in unique[1:] if a["kind"] != "resume"][:2]

    placement = max(
        (x for x in subject_assessments if x.status == "completed" and x.completed_at),
        key=lambda x: x.completed_at,
        default=None,
    )
    show = bool(
        placement
        and placement.completed_at
        and placement.completed_at > now - timedelta(days=3)
        and (last_session is None or last_session.started_at < placement.completed_at)
    )
    counts = {k: 0 for k in STATUS_LABEL}
    for sid, st in states.items():
        if sid in skills:
            counts[st.status] += 1
    counts["needs_assessment"] += len([s for s in skills if s not in states])
    goal = profile_service.goal_progress(db, user)
    db.commit()  # goal achievement timestamp
    return {
        "name": user.full_name.split(" ")[0],
        "subject": {"code": subject.code, "name": subject.name},
        "diagnostic_completed": diag_done,
        "next": nxt,
        "up_next": up_next,
        "reviews_due": reviews_due,
        "resume": resume,
        "pace_suggestion": _pace_suggestion(db, user, prof) if diag_done else None,
        "diagnosis_summary": {
            "strong": counts["likely_strength"],
            "getting_there": counts["developing"],
            "needs_practice": counts["potential_weakness"],
            "not_tried": counts["needs_assessment"],
            "show": show,
        },
        "streak": streak(db, user, prof.daily_goal),
        "goal": goal,
        "mixed": _mixed_info(db, user, subject, states),
    }


def answer_pace_suggestion(db: Session, user: User, accept: bool) -> None:
    prof = profile_service.require(db, user)
    suggestion = _pace_suggestion(db, user, prof)
    if accept and suggestion is not None:
        prof.pace_preference = suggestion["suggested"]
        state.refresh(db, user.id, prof.subject_id)
        recommend.generate(db, user.id, "profile", subject_id=prof.subject_id)
    prof.pace_suggestion_dismissed_at = datetime.now(UTC)
    db.commit()
