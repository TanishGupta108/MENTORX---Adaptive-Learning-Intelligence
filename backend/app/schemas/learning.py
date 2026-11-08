from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PathItemOut(BaseModel):
    position: int  # 1-based
    concept: str
    name: str
    reason: Literal["revision", "prerequisite", "weak", "new"]
    target_difficulty: int = Field(ge=1, le=3)
    mastery_at_generation: float | None
    mastery: float | None  # current estimate (null if never practised)
    explanation: str


class LearningPathOut(BaseModel):
    id: uuid.UUID
    subject: str
    trigger: str
    generated_at: datetime
    model_version: str | None
    items: list[PathItemOut]  # empty = nothing to recommend (everything mastered)


class RevisionItemOut(BaseModel):
    concept: str
    name: str
    peak: float
    mastery: float
    drop: float
    last_practised_at: datetime | None


class UpcomingRevisionOut(BaseModel):
    concept: str
    name: str
    peak: float
    mastery: float
    # First day (on a fixed grid of 1, 2, 3, 5, 7, 10, 14, ... days) on which the model
    # predicts mastery will be below the revision threshold without practice.
    # null = not within `horizon_days`.
    due_in_days: int | None


class RevisionOut(BaseModel):
    subject: str
    threshold: float
    due: list[RevisionItemOut]  # ordered by how far mastery has fallen (FR-REV-02)
    upcoming: list[UpcomingRevisionOut]  # FR-REV-05
    horizon_days: int
