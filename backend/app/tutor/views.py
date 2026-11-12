"""Read models for the student screens: catalog, diagnosis report, skill page, dashboard,
learning path and analytics. Observed performance and model predictions are always returned
in SEPARATE fields, and a prediction is null when the real model didn't produce one.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import User
from app.tutor import engine, kt, practice, recommend, resources, state
from app.tutor import profile as profile_service
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
)

STATUS_LABEL = {
    "likely_strength": "Likely Strength",
    "developing": "Developing",
    "potential_weakness": "Potential Weakness",
    "needs_assessment": "Needs Assessment",
}
MODE_LABEL = {
    "foundation": "Foundation",
    "guided": "Guided",
    "independent": "Independent",
    "advanced": "Advanced",
}


def _states(db: Session, user: User) -> dict[int, SkillState]:
    states = {
        s.skill_id: s for s in db.scalars(select(SkillState).where(SkillState.user_id == user.id))
    }
    if not states and profile_service.get(db, user):
        states = state.refresh(db, user.id)
        db.commit()
    return states


def skill_out(skill: Skill, st: SkillState | None) -> dict:
    attempts = st.attempts if st else 0
    recent = (st.recent or [])[-state.RECENT_WINDOW :] if st else []
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
        "mode": state.effective_mode(st) if st else "guided",
        "mode_label": MODE_LABEL[state.effective_mode(st) if st else "guided"],
        "mode_is_override": bool(st and st.mode_override),
        "completed": bool(st and st.completed_at),
        "reassessed_accuracy": st.reassessed_accuracy if st else None,
        "revision_due_at": st.revision_due_at if st else None,
        "last_practiced_at": st.last_practiced_at if st else None,
    }


def catalog(db: Session, user: User) -> dict:
    subject = profile_service.math_subject(db)
    states = _states(db, user)
    skills = list(
        db.scalars(
            select(Skill).where(Skill.is_available).order_by(Skill.grade, Skill.code, Skill.id)
        )
    )
    domains: dict[str, dict] = {}
    for s in skills:
        d = domains.setdefault(
            s.domain_code, {"code": s.domain_code, "name": s.domain_name, "skills": []}
        )
        d["skills"].append(skill_out(s, states.get(s.id)))
    return {
        "subject": {"code": subject.code, "name": subject.name, "description": subject.description},
        "n_skills": len(skills),
        "n_questions": sum(s.n_items for s in skills),
        "domains": sorted(domains.values(), key=lambda d: -len(d["skills"])),
        "model": kt.info().__dict__,
    }


def _recs_out(
    db: Session, user: User, states: dict[int, SkillState], limit: int | None = None
) -> list[dict]:
    out = []
    for r in recommend.current(db, user.id)[:limit]:
        skill = db.get(Skill, r.skill_id)
        n_res = db.scalar(
            select(func.count())
            .select_from(Resource)
            .where(Resource.skill_id == r.skill_id, Resource.is_active)
        )
        out.append(
            {
                "priority": r.priority,
                "reason_code": r.reason_code,
                "reason": r.reason_text,
                "activities": r.activities,
                "resources_available": int(n_res or 0),
                "skill": skill_out(skill, states.get(r.skill_id)),
            }
        )
    return out


def diagnosis(db: Session, user: User) -> dict:
    states = _states(db, user)
    a = db.scalar(
        select(Assessment)
        .where(
            Assessment.user_id == user.id,
            Assessment.status == "completed",
            Assessment.kind.in_(("diagnostic", "skill_check")),
        )
        .order_by(Assessment.completed_at.desc())
        .limit(1)
    )
    skills = {s.id: s for s in db.scalars(select(Skill).where(Skill.is_available))}
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
        headline = (
            f"Your recent performance suggests that {weak[0]['name']} may need additional practice."
        )
    elif strong:
        headline = f"You did well on {strong[0]['name']}. Let's build on that."
    else:
        headline = "We have a first picture of your skills. Practice will make it sharper."
    return {
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
        "recommendations": _recs_out(db, user, states, 3),
        "selection_trace": _diagnostic_trace(db, a) if a and a.kind == "diagnostic" else [],
        "model": kt.info().__dict__,
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
            "item_id": it.id,
            "body_html": it.body_html,
            "answer_type": it.answer_type,
            "options": it.options,
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


def skill_detail(db: Session, user: User, skill_id: int) -> dict:
    skill = db.get(Skill, skill_id)
    if skill is None or not skill.is_available:
        from app.core.errors import AppError

        raise AppError(404, "skill_not_found", "That skill isn't available.")
    states = _states(db, user)
    st = states.get(skill_id)
    base = skill_out(skill, st)
    res = resources.for_skill(db, user, skill_id)
    prereq_rows = db.execute(
        select(Skill, SkillPrerequisite.source)
        .join(SkillPrerequisite, SkillPrerequisite.prerequisite_id == Skill.id)
        .where(SkillPrerequisite.skill_id == skill_id, Skill.is_available)
    ).all()
    dependents = db.scalars(
        select(Skill)
        .join(SkillPrerequisite, SkillPrerequisite.skill_id == Skill.id)
        .where(SkillPrerequisite.prerequisite_id == skill_id, Skill.is_available)
    )
    last_re = _last_reassessment(db, user, skill_id)
    outcome = (last_re.result or {}).get("outcome") if last_re else None
    struggling = bool(st) and (
        outcome == "not_improved" or (st.status == "potential_weakness" and st.attempts >= 5)
    )
    support = None
    if struggling:
        weak_prereqs = [
            skill_out(p, states.get(p.id))
            for p, _ in prereq_rows
            if states.get(p.id) is None
            or states[p.id].status in ("potential_weakness", "needs_assessment", "developing")
        ]
        support = {
            "message": "Learning takes time. Let's strengthen the basics before moving ahead.",
            "steps": [
                "Look at your recent mistakes below and compare them with the correct answers.",
                "Re-read the key idea in the concept notes.",
                "Work through the worked example step by step.",
                "Practise in Foundation mode: easier questions, with hints available.",
                "Take a fresh reassessment when practice feels comfortable.",
            ],
            "prerequisites_to_check": weak_prereqs,
            "no_prerequisite_note": None
            if prereq_rows
            else "No curated prerequisite is mapped for this skill, so the plan focuses on foundational practice in the same skill.",
        }
    c_fresh = len(
        [
            i
            for i in db.scalars(engine.usable_items(db, skill_id))
            if i.id not in engine.attempted_item_ids(db, user.id)
        ]
    )
    cfg = get_settings()
    if not st or st.attempts == 0:
        nxt = {"action": "skill_check", "label": "Take a short skill check"}
    elif struggling:
        nxt = {
            "action": "foundation",
            "label": "Review the basics, then practise in Foundation mode",
        }
    elif (
        st.attempts >= 5
        and (st.correct / st.attempts) >= 0.65
        and not (st.completed_at and outcome == "improved")
    ):
        nxt = {"action": "reassess", "label": "Take a fresh reassessment"}
    else:
        nxt = {
            "action": "practice",
            "label": f"Continue {MODE_LABEL[state.effective_mode(st)]} practice",
        }
    return {
        **base,
        "description": skill.description,
        "standard_url": skill.standard_url,
        "difficulty_counts": dict(
            db.execute(
                select(Item.difficulty, func.count())
                .where(
                    Item.skill_id == skill_id,
                    Item.n_skills == 1,
                    Item.is_active,
                    Item.exclusion_reason.is_(None),
                )
                .group_by(Item.difficulty)
            ).all()
        ),
        "fresh_questions": c_fresh,
        "resources": res,
        "resources_done": sum(1 for r in res if r["completed"]),
        "prerequisites": [
            {**skill_out(p, states.get(p.id)), "source": src} for p, src in prereq_rows
        ],
        "leads_to": [skill_out(d, states.get(d.id)) for d in dependents],
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


def _daily(db: Session, user: User, days: int) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=days - 1)
    rows = db.execute(
        select(Interaction.created_at, Interaction.is_correct, Interaction.context).where(
            Interaction.user_id == user.id,
            Interaction.created_at >= since.replace(hour=0, minute=0, second=0),
        )
    ).all()
    agg: dict[date, list[int]] = defaultdict(lambda: [0, 0])
    for ts, ok, _ in rows:
        d = ts.astimezone(UTC).date()
        agg[d][0] += 1
        agg[d][1] += int(ok)
    out = []
    for i in range(days):
        d = (since + timedelta(days=i)).date()
        n, c = agg.get(d, [0, 0])
        out.append(
            {"date": d.isoformat(), "attempts": n, "correct": c, "accuracy": c / n if n else None}
        )
    return out


def _activity(db: Session, user: User, limit: int = 8) -> list[dict]:
    items: list[dict] = []
    for a in db.scalars(
        select(Assessment)
        .where(Assessment.user_id == user.id)
        .order_by(Assessment.started_at.desc())
        .limit(limit)
    ):
        skill = db.get(Skill, a.skill_id) if a.skill_id else None
        items.append(
            {
                "kind": a.kind,
                "title": {
                    "diagnostic": "Diagnostic assessment",
                    "skill_check": "Skill check",
                    "reassessment": "Reassessment",
                }[a.kind]
                + (f": {skill.name}" if skill else ""),
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
        .limit(limit)
    ):
        skill = db.get(Skill, p.skill_id) if p.skill_id else None
        title = (
            "Mixed practice"
            if p.kind == "mixed"
            else f"{'Guided practice' if p.guided else 'Practice'}: {skill.name}"
        )
        items.append(
            {
                "kind": "practice",
                "title": title,
                "detail": f"{p.correct_count}/{p.answered_count} correct · {MODE_LABEL[p.mode]} mode",
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


def dashboard(db: Session, user: User) -> dict:
    prof = profile_service.require(db, user)
    states = _states(db, user)
    skills = {s.id: s for s in db.scalars(select(Skill).where(Skill.is_available))}
    assessed = [st for sid, st in states.items() if sid in skills and st.attempts > 0]
    recs = _recs_out(db, user, states, 4)
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
    practised = practice.practised_skills(db, user.id)
    mixed_left = db.scalar(
        select(func.count()).select_from(engine.usable_items(db, mixed=True).subquery())
    )
    mc, mn = practice.mixed_accuracy(db, user.id)
    return {
        "name": user.full_name.split(" ")[0],
        "diagnostic_completed": prof.diagnostic_completed_at is not None,
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
        "progress": _daily(db, user, 14),
        "activity": _activity(db, user, 6),
        "goal": goal,
        "streak": streak(db, user, prof.daily_goal),
        "mixed": {
            "available": len(practised) >= practice.MIXED_MIN_SKILLS and bool(mixed_left),
            "skills_practised": len(practised),
            "needs_skills": practice.MIXED_MIN_SKILLS,
            "questions": int(mixed_left or 0),
            "answered": mn,
            "accuracy": mc / mn if mn else None,
        },
        "model": kt.info().__dict__,
    }


def streak(db: Session, user: User, daily_goal: int) -> dict:
    """Days in a row with at least one answer (UTC days), and today's count vs the goal.
    A streak stays alive until the end of the next day."""
    since = datetime.now(UTC) - timedelta(days=400)
    stamps = db.scalars(
        select(Interaction.created_at).where(
            Interaction.user_id == user.id, Interaction.created_at >= since
        )
    ).all()
    days = {t.astimezone(UTC).date() for t in stamps}
    today = datetime.now(UTC).date()
    today_count = sum(1 for t in stamps if t.astimezone(UTC).date() == today)
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


def learning_path(db: Session, user: User) -> dict:
    profile_service.require(db, user)
    states = _states(db, user)
    skills = {s.id: s for s in db.scalars(select(Skill).where(Skill.is_available))}
    recs = recommend.current(db, user.id)
    done_by_skill: dict[int, int] = defaultdict(int)
    total_by_skill: dict[int, int] = defaultdict(int)
    done = resources.completed_ids(db, user)
    for r in db.scalars(select(Resource).where(Resource.is_active, Resource.kind != "standard")):
        if r.skill_id:
            total_by_skill[r.skill_id] += 1
            done_by_skill[r.skill_id] += int(r.id in done)

    def step(sid: int, label: str, reason: str | None, activities: list[str] | None) -> dict:
        st = states.get(sid)
        so = skill_out(skills[sid], st)
        return {
            "skill": so,
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
            f"Reassessment {round(100 * (st.reassessed_accuracy or 0))}% correct",
            ["Review when revision is due"],
        )
        for sid, st in states.items()
        if sid in skills and st.completed_at and sid not in seen
    ]
    return {"steps": steps, "completed": completed}


def analytics(db: Session, user: User) -> dict:
    profile_service.require(db, user)
    states = _states(db, user)
    skills = {s.id: s for s in db.scalars(select(Skill))}
    rows = db.execute(
        select(Interaction.context, Interaction.is_correct, Interaction.hint_used).where(
            Interaction.user_id == user.id
        )
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
        .where(Assessment.user_id == user.id, Assessment.status == "completed")
        .order_by(Assessment.completed_at)
    ).all()
    sessions = db.scalars(
        select(PracticeSession)
        .where(PracticeSession.user_id == user.id, PracticeSession.answered_count > 0)
        .order_by(PracticeSession.started_at)
    ).all()
    res_done = db.scalar(
        select(func.count())
        .select_from(ResourceCompletion)
        .where(ResourceCompletion.user_id == user.id)
    )
    res_total = db.scalar(
        select(func.count())
        .select_from(Resource)
        .where(Resource.is_active, Resource.kind != "standard")
    )
    return {
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
                *practice.mixed_accuracy(db, user.id)
            ),
            "assessments": len(assessments),
            "practice_sessions": len(sessions),
            "resources_completed": int(res_done or 0),
            "resources_total": int(res_total or 0),
        },
        "daily": _daily(db, user, 30),
        "skills": skill_rows,
        "assessments": [
            {
                "id": a.id,
                "kind": a.kind,
                "skill": skills[a.skill_id].name if a.skill_id else None,
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
                "skill": skills[p.skill_id].name if p.skill_id else "Mixed practice",
                "kind": p.kind,
                "mode": p.mode,
                "accuracy": p.correct_count / max(p.answered_count, 1),
                "answered": p.answered_count,
                "started_at": p.started_at,
            }
            for p in sessions
        ],
        "activity": _activity(db, user, 12),
        "model": kt.info().__dict__,
    }
