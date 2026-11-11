"""Recommendations and the learning path, with a plain-language reason for each one.

Priority order (product brief, step 7):
1. the student's chosen focus skill (onboarding goal "learn a specific topic");
2. evidence-supported potential weaknesses (weakest first);
3. skills due for revision;
4. developing skills;
5. skills needing assessment: first those that are curated prerequisites of a weak skill,
   then the core skills the model expects to be hardest. The model only ORDERS these;
   it never turns them into a weakness.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.tutor.models import Recommendation, Skill, SkillPrerequisite, SkillState, StudentProfile
from app.tutor.state import MODE_POLICY, effective_mode

MAX_RECOMMENDATIONS = 6
CORE_MIN_ITEMS = 20


def pct(x: float | None) -> str:
    return "—" if x is None else f"{round(100 * x)}%"


def activities_for(mode: str, has_attempts: bool) -> list[str]:
    plan = {
        "foundation": [
            "Read the concept notes",
            "Study the worked example",
            "Guided practice with easy questions and hints",
        ],
        "guided": [
            "Review the concept notes",
            "Study the worked example",
            "Guided practice, easy to medium",
        ],
        "independent": ["Practise medium-to-hard questions", "Take a short reassessment"],
        "advanced": ["Challenge practice with hard questions", "Take a reassessment to confirm"],
    }[mode]
    if not has_attempts:
        return ["Take a short skill check", *plan[:2]]
    return plan


def _reason(code: str, skill: Skill, st: SkillState, extra: str = "") -> str:
    acc = st.correct / st.attempts if st.attempts else None
    if code == "focus":
        return f"You chose {skill.name} as your focus topic."
    if code == "weakness":
        return (
            f"{skill.name} is recommended because your answers so far ({st.correct} of {st.attempts} correct, "
            f"{pct(acc)}) suggest you may benefit from additional practice."
        )
    if code == "revision":
        return f"You completed {skill.name} a while ago. A short review now helps you keep it."
    if code == "developing":
        return (
            f"You're developing {skill.name} ({st.correct} of {st.attempts} correct). "
            "A little more practice should make it solid."
        )
    if code == "prerequisite":
        return (
            f"{skill.name} hasn't been assessed yet, and it is a building block for {extra}, "
            "which you found difficult. Checking it first may explain those mistakes."
        )
    if code == "next_objective":
        return (
            f"{skill.name} builds on {extra}, which you have completed. It's a natural next step."
        )
    return f"{skill.name} hasn't been assessed yet. A short check will show where you stand" + (
        f"; the model expects it to be one of your harder topics ({pct(st.predicted_p)} predicted success)."
        if st.predicted_p is not None
        else "."
    )


def generate(
    db: Session, user_id: uuid.UUID, trigger: str, now: datetime | None = None
) -> list[Recommendation]:
    now = now or datetime.now(UTC)
    profile = db.get(StudentProfile, user_id)
    skills = {s.id: s for s in db.scalars(select(Skill).where(Skill.is_available))}
    states = {
        s.skill_id: s
        for s in db.scalars(select(SkillState).where(SkillState.user_id == user_id))
        if s.skill_id in skills
    }
    prereqs: dict[int, list[int]] = {}
    for p in db.scalars(select(SkillPrerequisite)):
        prereqs.setdefault(p.skill_id, []).append(p.prerequisite_id)
    dependents: dict[int, list[int]] = {}
    for s, ps in prereqs.items():
        for p in ps:
            dependents.setdefault(p, []).append(s)

    picked: list[tuple[int, str, str]] = []
    seen: set[int] = set()

    def add(sid: int, code: str, extra: str = "") -> None:
        if sid in seen or sid not in states or len(picked) >= MAX_RECOMMENDATIONS:
            return
        seen.add(sid)
        picked.append((sid, code, _reason(code, skills[sid], states[sid], extra)))

    if profile and profile.goal_type == "learn_topic" and profile.focus_skill_id in states:
        st = states[profile.focus_skill_id]
        if not (st.completed_at and st.status == "likely_strength"):
            add(profile.focus_skill_id, "focus")

    weak = sorted(
        (s for s in states.values() if s.status == "potential_weakness"),
        key=lambda s: (
            s.correct / max(s.attempts, 1),
            s.predicted_p if s.predicted_p is not None else 1,
        ),
    )
    for s in weak:
        add(s.skill_id, "weakness")
    for s in states.values():
        if s.revision_due_at and s.revision_due_at <= now:
            add(s.skill_id, "revision")
    for s in sorted(
        (s for s in states.values() if s.status == "developing"),
        key=lambda s: s.correct / max(s.attempts, 1),
    ):
        add(s.skill_id, "developing")
    # unassessed building blocks of weak skills
    for w in weak:
        for p in prereqs.get(w.skill_id, []):
            if p in states and states[p].status == "needs_assessment":
                add(p, "prerequisite", skills[w.skill_id].name)
    # next objectives after completed skills
    for s in states.values():
        if s.completed_at:
            for d in dependents.get(s.skill_id, []):
                if d in states and not states[d].completed_at:
                    add(d, "next_objective", skills[s.skill_id].name)
    # unassessed core skills, the ones the model expects to be hardest first
    unassessed = [
        s
        for s in states.values()
        if s.status == "needs_assessment" and skills[s.skill_id].n_items >= CORE_MIN_ITEMS
    ]
    for s in sorted(
        unassessed,
        key=lambda s: (
            s.predicted_p if s.predicted_p is not None else 0.5,
            skills[s.skill_id].grade or 0,
        ),
    ):
        add(s.skill_id, "needs_assessment")

    db.execute(
        update(Recommendation)
        .where(Recommendation.user_id == user_id, Recommendation.is_current)
        .values(is_current=False)
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
    if profile and recs:
        profile.current_skill_id = recs[0].skill_id
    db.flush()
    return recs


def current(db: Session, user_id: uuid.UUID) -> list[Recommendation]:
    return list(
        db.scalars(
            select(Recommendation)
            .where(Recommendation.user_id == user_id, Recommendation.is_current)
            .order_by(Recommendation.priority)
        )
    )


def mode_policy(mode: str) -> dict:
    return MODE_POLICY[mode]
