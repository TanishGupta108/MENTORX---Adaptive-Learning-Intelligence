from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


class ConceptMastery(BaseModel):
    concept: str
    name: str
    mastery: float
    n_attempts: int


class ActiveSession(BaseModel):
    id: uuid.UUID
    type: str
    answered: int
    target: int


class DashboardOut(BaseModel):
    """FR-DASH-01/03. Every number comes from the student's real attempts and the model.

    Values are null (never a placeholder) when there's no data yet (FR-DASH-08).
    """

    subject: str
    diagnostic_completed: bool
    concepts_total: int
    concepts_assessed: int  # concepts with a stored mastery estimate
    concepts_mastered: int  # mastery >= mastered threshold
    mastered_threshold: float
    mean_mastery: float | None  # over assessed concepts
    questions_answered: int
    accuracy: float | None
    sessions_completed: int
    strongest: list[ConceptMastery]  # >= 3 attempts each
    weakest: list[ConceptMastery]
    active_sessions: list[ActiveSession]


class TrendPoint(BaseModel):
    day: date
    answered: int
    accuracy: float | None  # null on days without answers
    mean_mastery: float | None  # end of day; null before the first estimate


class TrendsOut(BaseModel):
    subject: str
    days: int
    points: list[TrendPoint]


class ActivityDay(BaseModel):
    day: date
    answered: int


class ActivityOut(BaseModel):
    weeks: int
    timezone: str
    days: list[ActivityDay]  # oldest first, every day included (0 when inactive)


class FlagRequest(BaseModel):
    comment: str = Field(default="", max_length=1000)


class FlagOut(BaseModel):
    id: int
    question_id: int
    status: str
