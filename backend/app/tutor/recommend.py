"""Recommendations and the learning path for ONE subject, with a plain one-sentence reason.

Priority order (product brief, step 7, plus v3 personalization):
1. the student's chosen focus skill (onboarding goal "learn a specific topic");
2. skills the student is stuck on (many answers, never mastered, recent accuracy low);
3. evidence-supported potential weaknesses (weakest first);
4. skills due for a spaced review;
5. developing skills;
6. skills needing assessment that are curated prerequisites of a weak skill;
7. next objectives after completed skills (near the student's grade first);
8. core skills needing assessment, near the student's grade first, then the ones the model
   expects to be hardest. The model only ORDERS these; it never turns them into a weakness.
Recommendations are regenerated after practice/assessments and on read when older than
`recommendations_stale_hours`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Subject
from app.tutor import state as state_rules
from app.tutor.models import Recommendation, Skill, SkillPrerequisite, SkillState, StudentProfile
from app.tutor.state import MODE_POLICY, effective_mode
from app.tutor.subjects import meta as subject_meta

MAX_RECOMMENDATIONS = 6


def pct(x: float | None) -> str:
    return "—" if x is None else f"{round(100 * x)}%"


def activities_for(mode: str, has_attempts: bool) -> list[str]:
    plan = {
        "foundation": [
            "Read the concept notes",
            "Study the worked example",
            "Step-by-step practice with easy questions and hints",
        ],
        "guided": [
            "Review the concept notes",
            "Study the worked example",
            "Guided practice, easy to medium",
        ],
        "independent": ["Practise medium-to-hard questions", "Take a short check"],
        "advanced": ["Challenge practice with hard questions", "Take a check to confirm"],
    }[mode]
    if not has_attempts:
        return ["Take a short skill check", *plan[:2]]
    return plan


def _reason(code: str, skill: Skill, extra: str = "") -> str:
    """One plain sentence (no model numbers): shown behind "Why?"."""
    return {
        "focus": f"You chose {skill.name} as your focus topic.",
        "stuck": (
            f"This one is tricky right now. Let's strengthen {extra} first."
            if extra
            else "This one is tricky right now. Let's look at the worked example and try a few "
            "step-by-step questions."
        ),
        "weakness": "Your answers so far show this skill needs more practice.",
        "review": "You learned this a while ago. A quick review helps you keep it.",
        "revision": "You learned this a while ago. A quick review helps you keep it.",
        "developing": "You're getting there. A little more practice should make it solid.",
        "prerequisite": f"It's a building block for {extra}, which you found tricky.",
        "next_objective": f"It builds on {extra}, which you have completed.",
    }.get(code, "You haven't tried this yet. A short check will show where you stand.")


def prerequisite_map(db: Session, skill_ids: set[int]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for p in db.scalars(select(SkillPrerequisite).where(SkillPrerequisite.skill_id.in_(skill_ids))):
        if p.prerequisite_id in skill_ids:
            out.setdefault(p.skill_id, []).append(p.prerequisite_id)
    return out


def unmet_prerequisite(
    sid: int,
    prereqs: dict[int, list[int]],
    states: dict[int, SkillState],
    skills: dict[int, Skill],
) -> int | None:
    """A curated prerequisite of `sid` that isn't Strong yet (lowest grade first)."""
    cands = [
        p
        for p in prereqs.get(sid, [])
        if p in skills and (p not in states or states[p].status != "likely_strength")
    ]
    cands.sort(key=lambda p: (skills[p].grade or 0, skills[p].code))
    return cands[0] if cands else None


def generate(
    db: Session,
    user_id: uuid.UUID,
    trigger: str,
    now: datetime | None = None,
    subject_id: int | None = None,
) -> list[Recommendation]:
    now = now or datetime.now(UTC)
    profile = db.get(StudentProfile, user_id)
    if subject_id is None:
        subject_id = profile.subject_id if profile else None
    if subject_id is None:
        return []
    subject = db.get(Subject, subject_id)
    core_min = subject_meta(subject.code if subject else None)["core_min_items"]
    skills = {
        s.id: s
        for s in db.scalars(select(Skill).where(Skill.subject_id == subject_id, Skill.is_available))
    }
    states = {
        s.skill_id: s
        for s in db.scalars(select(SkillState).where(SkillState.user_id == user_id))
        if s.skill_id in skills
    }
    prereqs = prerequisite_map(db, set(skills))
    dependents: dict[int, list[int]] = {}
    for s, ps in prereqs.items():
        for p in ps:
            dependents.setdefault(p, []).append(s)
    grade = profile.grade if profile else None

    def near_grade(sid: int) -> int:
        g = skills[sid].grade
        return 0 if grade is None or g is None or g <= grade + 1 else 1

    picked: list[tuple[int, str, str]] = []
    seen: set[int] = set()

    def add(sid: int, code: str, extra: str = "") -> None:
        if sid in seen or sid not in states or len(picked) >= MAX_RECOMMENDATIONS:
            return
        seen.add(sid)
        picked.append((sid, code, _reason(code, skills[sid], extra)))

    if profile and profile.goal_type == "learn_topic" and profile.focus_skill_id in states:
        st = states[profile.focus_skill_id]
        if not (st.completed_at and st.status == "likely_strength"):
            add(profile.focus_skill_id, "focus")

    for s in states.values():
        if state_rules.is_stuck(s.attempts, list(s.recent or []), s.mastered_at):
            pre = unmet_prerequisite(s.skill_id, prereqs, states, skills)
            add(s.skill_id, "stuck", skills[pre].name if pre else "")
    weak = sorted(
        (s for s in states.values() if s.status == "potential_weakness"),
        key=lambda s: (
            s.correct / max(s.attempts, 1),
            s.predicted_p if s.predicted_p is not None else 1,
        ),
    )
    for s in weak:
        add(s.skill_id, "weakness")
    for s in sorted(
        (s for s in states.values() if s.revision_due_at and s.revision_due_at <= now),
        key=lambda s: s.revision_due_at,
    ):
        add(s.skill_id, "review")
    for s in sorted(
        (s for s in states.values() if s.status == "developing"),
        key=lambda s: s.correct / max(s.attempts, 1),
    ):
        add(s.skill_id, "developing")
    for w in weak:  # unassessed building blocks of weak skills
        for p in prereqs.get(w.skill_id, []):
            if p in states and states[p].status == "needs_assessment":
                add(p, "prerequisite", skills[w.skill_id].name)
    nexts = []
    for s in states.values():  # next objectives after completed skills
        if s.completed_at:
            for d in dependents.get(s.skill_id, []):
                if d in states and not states[d].completed_at:
                    nexts.append((near_grade(d), d, skills[s.skill_id].name))
    for _, d, name in sorted(nexts):
        add(d, "next_objective", name)
    unassessed = [
        s
        for s in states.values()
        if s.status == "needs_assessment" and skills[s.skill_id].n_items >= core_min
    ]
    for s in sorted(
        unassessed,
        key=lambda s: (
            near_grade(s.skill_id),
            abs((skills[s.skill_id].grade or 0) - (grade or 0)) if grade else 0,
            s.predicted_p if s.predicted_p is not None else 0.5,
            skills[s.skill_id].grade or 0,
        ),
    ):
        add(s.skill_id, "needs_assessment")

    db.execute(
        update(Recommendation)
        .where(
            Recommendation.user_id == user_id,
            Recommendation.is_current,
            Recommendation.skill_id.in_(select(Skill.id).where(Skill.subject_id == subject_id)),
        )
        .values(is_current=False)
        .execution_options(synchronize_session=False)
    )
    recs = []
    for i, (sid, code, text) in enumerate(picked):
        st = states[sid]
        r = Recommendation(
            user_id=user_id,
            skill_id=sid,
            priority=i + 1,
            reason_code=code,
            reason_text=text,
            activities=activities_for(effective_mode(st), st.attempts > 0),
            trigger=trigger,
            is_current=True,
            created_at=now,
        )
        db.add(r)
        recs.append(r)
    if profile and recs and profile.subject_id == subject_id:
        profile.current_skill_id = recs[0].skill_id
    db.flush()
    return recs


def current(db: Session, user_id: uuid.UUID, subject_id: int | None = None) -> list[Recommendation]:
    stmt = select(Recommendation).where(
        Recommendation.user_id == user_id, Recommendation.is_current
    )
    if subject_id is not None:
        stmt = stmt.join(Skill, Skill.id == Recommendation.skill_id).where(
            Skill.subject_id == subject_id
        )
    return list(db.scalars(stmt.order_by(Recommendation.priority)))


def current_fresh(
    db: Session, user_id: uuid.UUID, subject_id: int, now: datetime | None = None
) -> list[Recommendation]:
    """Current recommendations, regenerated first when none exist or they are stale."""
    now = now or datetime.now(UTC)
    recs = current(db, user_id, subject_id)
    stale = timedelta(hours=get_settings().recommendations_stale_hours)
    if not recs or max(r.created_at for r in recs) < now - stale:
        recs = generate(db, user_id, "refresh", now, subject_id)
        db.commit()
    return recs


def mode_policy(mode: str) -> dict:
    return MODE_POLICY[mode]
