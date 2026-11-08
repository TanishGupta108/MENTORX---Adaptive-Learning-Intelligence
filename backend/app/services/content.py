"""Subjects, enrolment and concepts (FR-CONT-01/02, FR-DASH-02)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Concept, ConceptPrerequisite, Enrollment, Mastery, Subject, User
from app.ml.registry import get_model
from app.schemas.content import ConceptOut, EnrollmentOut, SubjectOut
from app.services import mastery as mastery_service


def _subject(db: Session, code: str) -> Subject:
    subject = db.scalar(select(Subject).where(Subject.code == code.upper(), Subject.is_active))
    if subject is None:
        raise AppError(404, "subject_not_found", f"No active subject with code {code!r}.")
    return subject


def list_subjects(db: Session, user: User) -> list[SubjectOut]:
    counts = (
        select(Concept.subject_id, func.count().label("n")).group_by(Concept.subject_id).subquery()
    )
    rows = db.execute(
        select(Subject, func.coalesce(counts.c.n, 0), Enrollment.user_id.is_not(None))
        .outerjoin(counts, counts.c.subject_id == Subject.id)
        .outerjoin(
            Enrollment, (Enrollment.subject_id == Subject.id) & (Enrollment.user_id == user.id)
        )
        .where(Subject.is_active)
        .order_by(Subject.name)
    ).all()
    return [
        SubjectOut(
            code=s.code,
            name=s.name,
            description=s.description,
            concept_count=n,
            enrolled=bool(enrolled),
        )
        for s, n, enrolled in rows
    ]


def enroll(db: Session, user: User, code: str) -> EnrollmentOut:
    subject = _subject(db, code)
    # Idempotent: enrolling twice is not an error.
    db.execute(
        insert(Enrollment)
        .values(user_id=user.id, subject_id=subject.id)
        .on_conflict_do_nothing(index_elements=["user_id", "subject_id"])
    )
    db.commit()
    e = db.get(Enrollment, (user.id, subject.id))
    return EnrollmentOut(
        subject=subject.code,
        enrolled=True,
        diagnostic_completed=e.diagnostic_completed_at is not None,
    )


def list_concepts(db: Session, user: User, code: str) -> list[ConceptOut]:
    subject = _subject(db, code)
    concepts = db.scalars(
        select(Concept).where(Concept.subject_id == subject.id).order_by(Concept.topo_order)
    ).all()
    by_id = {c.id: c.code for c in concepts}
    prereqs: dict[int, list[str]] = {c.id: [] for c in concepts}
    for cid, pid in db.execute(
        select(ConceptPrerequisite.concept_id, ConceptPrerequisite.prerequisite_id).where(
            ConceptPrerequisite.concept_id.in_(by_id)
        )
    ):
        prereqs[cid].append(by_id[pid])
    stored = set(
        db.scalars(
            select(Mastery.concept_id).where(
                Mastery.user_id == user.id, Mastery.concept_id.in_(by_id)
            )
        )
    )
    # Stored values older than a day are recomputed, so the map shows decay (FR-KT-04).
    mastery = (
        mastery_service.current(
            db,
            get_model(db),
            user.id,
            subject.id,
            [c for c in concepts if c.id in stored],
            datetime.now(UTC),
        )
        if stored
        else {}
    )
    db.commit()
    return [
        ConceptOut(
            code=c.code,
            name=c.name,
            description=c.description,
            topo_order=c.topo_order,
            prerequisites=sorted(prereqs[c.id]),
            mastery=mastery[c.id].p if c.id in mastery else None,
            n_attempts=mastery[c.id].n_attempts if c.id in mastery else 0,
        )
        for c in concepts
    ]
