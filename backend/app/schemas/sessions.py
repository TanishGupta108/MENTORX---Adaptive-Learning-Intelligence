from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=20)
    type: Literal["diagnostic", "practice"]
    concept: str | None = Field(default=None, description="practice only: focus on one concept")


class SessionOut(BaseModel):
    id: uuid.UUID
    subject: str
    type: str
    status: str
    focus_concept: str | None
    answered: int
    target: int
    started_at: datetime
    ended_at: datetime | None
    correct: int | None = None  # filled in history views


class OptionOut(BaseModel):
    key: str
    text: str


class QuestionOut(BaseModel):
    """What the student sees. Never includes the answer or explanation (FR-CONT-08)."""

    session_id: uuid.UUID
    question_id: int
    concept: str
    concept_name: str
    stem: str
    options: list[OptionOut]
    allow_dont_know: bool
    position: int  # 1-based
    total: int


class AnswerRequest(BaseModel):
    question_id: int
    selected_key: Literal["A", "B", "C", "D"] | None = Field(
        default=None, description="null = 'I don't know yet'"
    )


class MasteryChange(BaseModel):
    concept: str
    before: float | None
    after: float


class Feedback(BaseModel):
    correct: bool
    correct_key: str
    explanation: str


class ConceptSummary(BaseModel):
    concept: str
    name: str
    mastery: float


class DiagnosticSummary(BaseModel):
    strongest: list[ConceptSummary]
    weakest: list[ConceptSummary]


class AnswerResult(BaseModel):
    # Diagnostic answers get no per-question feedback (FR-DIAG-03); practice answers do.
    feedback: Feedback | None
    mastery: MasteryChange | None
    answered: int
    target: int
    session_complete: bool
    summary: DiagnosticSummary | None = None
