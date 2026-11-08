"""Learning paths and the revision queue, backed by the database (FR-PATH, FR-REV).

The rules live in `recommend` (pure functions); this module loads mastery through
`mastery.current` (which refreshes stale values with the ML model), stores paths and
keeps their history (FR-PATH-05).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import (
    Concept,
    ConceptPrerequisite,
    Enrollment,
    LearningPath,
    LearningPathItem,
    ModelVersion,
    Subject,
    User,
)
from app.ml import knowledge
from app.ml.registry import get_model
from app.schemas.learning import (
    LearningPathOut,
    PathItemOut,
    RevisionItemOut,
    RevisionOut,
    UpcomingRevisionOut,
)
from app.services import mastery as mastery_service
from app.services.mastery import ConceptState
from app.services.recommend import Rules, build_path, revision_due

PROJECTION_DAYS = (1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60, 90, 120, 150, 180, 270, 365)


def _now() -> datetime:
    return datetime.now(UTC)


def subject_for(db: Session, user: User, code: str) -> Subject:
    s = db.scalar(select(Subject).where(Subject.code == code.upper(), Subject.is_active))
    if s is None:
        raise AppError(404, "subject_not_found", f"No active subject with code {code!r}.")
    if db.get(Enrollment, (user.id, s.id)) is None:
        raise AppError(409, "not_enrolled", f"Enrol in {s.code} first.")
    return s


def concepts_of(db: Session, subject_id: int) -> list[Concept]:
    return list(
        db.scalars(
            select(Concept).where(Concept.subject_id == subject_id).order_by(Concept.topo_order)
        )
    )


def prerequisites(db: Session, concept_ids: list[int]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for cid, pid in db.execute(
        select(ConceptPrerequisite.concept_id, ConceptPrerequisite.prerequisite_id).where(
            ConceptPrerequisite.concept_id.in_(concept_ids)
        )
    ):
        out.setdefault(cid, []).append(pid)
    return out


def states(db: Session, user: User, subject_id: int, now: datetime) -> dict[int, ConceptState]:
    return mastery_service.current(
        db, get_model(db), user.id, subject_id, concepts_of(db, subject_id), now
    )


# ---------------------------------------------------------------- learning path


def generate(
    db: Session,
    user: User,
    subject_id: int,
    trigger: str,
    now: datetime | None = None,
    current: dict[int, ConceptState] | None = None,
) -> LearningPath:
    """Build and store a new current path; the old one is kept (FR-PATH-05). Caller commits."""
    now = now or _now()
    # One generator at a time per student and subject (the "one current path" index).
    db.execute(
        select(Enrollment)
        .where(Enrollment.user_id == user.id, Enrollment.subject_id == subject_id)
        .with_for_update()
    )
    current = current if current is not None else states(db, user, subject_id, now)
    recs = build_path(
        current, prerequisites(db, list(current)), Rules.from_settings(get_settings()), now
    )
    db.execute(
        update(LearningPath)
        .where(
            LearningPath.user_id == user.id,
            LearningPath.subject_id == subject_id,
            LearningPath.is_current,
        )
        .values(is_current=False)
    )
    db.flush()
    path = LearningPath(
        user_id=user.id,
        subject_id=subject_id,
        trigger=trigger,
        model_version_id=get_model(db).version_id,
        generated_at=now,
    )
    db.add(path)
    db.flush()
    for i, r in enumerate(recs, start=1):
        db.add(
            LearningPathItem(
                path_id=path.id,
                position=i,
                concept_id=r.concept_id,
                reason=r.reason,
                target_difficulty=r.target_difficulty,
                mastery_at_generation=r.mastery,
                explanation=r.explanation,
            )
        )
    db.flush()
    return path


def _current_path(db: Session, user_id: uuid.UUID, subject_id: int) -> LearningPath | None:
    return db.scalar(
        select(LearningPath).where(
            LearningPath.user_id == user_id,
            LearningPath.subject_id == subject_id,
            LearningPath.is_current,
        )
    )


def _items(db: Session, path: LearningPath) -> list[LearningPathItem]:
    return list(
        db.scalars(
            select(LearningPathItem)
            .where(LearningPathItem.path_id == path.id)
            .order_by(LearningPathItem.position)
        )
    )


def ensure_current(
    db: Session, user: User, subject_id: int, now: datetime | None = None
) -> tuple[LearningPath, dict[int, ConceptState]]:
    """The current path, generating it if there is none or if revisions have become due
    that it doesn't include (FR-PATH-04). Caller commits."""
    now = now or _now()
    current = states(db, user, subject_id, now)
    path = _current_path(db, user.id, subject_id)
    if path is None:
        path = generate(db, user, subject_id, "manual", now, current)
    else:
        due = {s.concept.id for s in revision_due(list(current.values()), _rules())}
        listed = {i.concept_id for i in _items(db, path) if i.reason == "revision"}
        if due - listed:
            path = generate(db, user, subject_id, "revision", now, current)
    return path, current


def _rules() -> Rules:
    return Rules.from_settings(get_settings())


def path_out(
    db: Session, path: LearningPath, current: dict[int, ConceptState], subject: Subject
) -> LearningPathOut:
    mv = db.get(ModelVersion, path.model_version_id) if path.model_version_id else None
    concepts = {c.id: c for c in concepts_of(db, subject.id)}
    return LearningPathOut(
        id=path.id,
        subject=subject.code,
        trigger=path.trigger,
        generated_at=path.generated_at,
        model_version=mv.name if mv else None,
        items=[
            PathItemOut(
                position=i.position,
                concept=concepts[i.concept_id].code,
                name=concepts[i.concept_id].name,
                reason=i.reason,
                target_difficulty=i.target_difficulty,
                mastery_at_generation=i.mastery_at_generation,
                mastery=(
                    current[i.concept_id].p
                    if i.concept_id in current and current[i.concept_id].attempted
                    else None
                ),
                explanation=i.explanation,
            )
            for i in _items(db, path)
        ],
    )


def get_path(db: Session, user: User, code: str) -> LearningPathOut:
    subject = subject_for(db, user, code)
    path, current = ensure_current(db, user, subject.id)
    db.commit()
    return path_out(db, path, current, subject)


def regenerate_path(db: Session, user: User, code: str) -> LearningPathOut:
    subject = subject_for(db, user, code)
    now = _now()
    current = states(db, user, subject.id, now)
    path = generate(db, user, subject.id, "manual", now, current)
    db.commit()
    return path_out(db, path, current, subject)


def path_concepts(db: Session, user: User, subject_id: int, n: int) -> list[int]:
    """The first `n` concepts of the current path (what a recommended practice draws from)."""
    path, _ = ensure_current(db, user, subject_id)
    return [i.concept_id for i in _items(db, path)[:n]]


# ---------------------------------------------------------------- revision


def due_concepts(db: Session, user: User, subject_id: int) -> list[ConceptState]:
    return revision_due(list(states(db, user, subject_id, _now()).values()), _rules())


def revision_queue(db: Session, user: User, code: str) -> RevisionOut:
    subject = subject_for(db, user, code)
    cfg = get_settings()
    rules = _rules()
    now = _now()
    current = states(db, user, subject.id, now)
    due = revision_due(list(current.values()), rules)

    # FR-REV-05: concepts that qualify for revision later (peaked, still above the floor):
    # ask the model when their mastery will fall below the floor without practice.
    watch = [
        s
        for s in current.values()
        if s.attempted
        and s.peak is not None
        and s.peak >= rules.revision_peak
        and s.p >= rules.revision_floor
    ]
    days = [d for d in PROJECTION_DAYS if d <= cfg.revision_projection_days]
    projected = knowledge.concept_mastery_at(
        db,
        get_model(db),
        user.id,
        subject.id,
        [s.concept for s in watch],
        [now + timedelta(days=d) for d in days],
    )
    upcoming = []
    for s in watch:
        ps = projected.get(s.concept.id, [])
        first = next((d for d, p in zip(days, ps, strict=True) if p < rules.revision_floor), None)
        upcoming.append(
            UpcomingRevisionOut(
                concept=s.concept.code,
                name=s.concept.name,
                peak=s.peak,
                mastery=s.p,
                due_in_days=first,
            )
        )
    upcoming.sort(key=lambda u: (u.due_in_days is None, u.due_in_days or 0, u.concept))
    db.commit()  # stale mastery may have been refreshed
    return RevisionOut(
        subject=subject.code,
        threshold=rules.revision_floor,
        due=[
            RevisionItemOut(
                concept=s.concept.code,
                name=s.concept.name,
                peak=s.peak,
                mastery=s.p,
                drop=s.peak - s.p,
                last_practised_at=s.last_attempt_at,
            )
            for s in due
        ],
        upcoming=upcoming,
        horizon_days=days[-1] if days else 0,
    )
