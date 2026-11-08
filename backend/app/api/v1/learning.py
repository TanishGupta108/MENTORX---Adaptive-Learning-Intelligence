from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DB, CurrentUser
from app.schemas.learning import LearningPathOut, RevisionOut
from app.services import learning

router = APIRouter(tags=["learning"])

SubjectCode = Annotated[str, Query(min_length=1, max_length=20, description="e.g. ML")]


@router.get("/learning-path", response_model=LearningPathOut)
def get_learning_path(subject: SubjectCode, user: CurrentUser, db: DB) -> LearningPathOut:
    """The current learning path. Regenerated automatically when revisions fall due."""
    return learning.get_path(db, user, subject)


@router.post("/learning-path/regenerate", response_model=LearningPathOut)
def regenerate_learning_path(subject: SubjectCode, user: CurrentUser, db: DB) -> LearningPathOut:
    """Build a fresh path now (the previous one is kept in history)."""
    return learning.regenerate_path(db, user, subject)


@router.get("/revision", response_model=RevisionOut)
def get_revision_queue(subject: SubjectCode, user: CurrentUser, db: DB) -> RevisionOut:
    """Concepts due for revision, and when others are projected to become due."""
    return learning.revision_queue(db, user, subject)
