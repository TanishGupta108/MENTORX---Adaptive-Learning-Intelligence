from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.schemas.content import ConceptOut, EnrollmentOut, SubjectOut
from app.services import content

router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.get("", response_model=list[SubjectOut])
def list_subjects(user: CurrentUser, db: DB) -> list[SubjectOut]:
    return content.list_subjects(db, user)


@router.post("/{code}/enroll", response_model=EnrollmentOut)
def enroll(code: str, user: CurrentUser, db: DB) -> EnrollmentOut:
    return content.enroll(db, user, code)


@router.get("/{code}/concepts", response_model=list[ConceptOut])
def list_concepts(code: str, user: CurrentUser, db: DB) -> list[ConceptOut]:
    return content.list_concepts(db, user, code)
