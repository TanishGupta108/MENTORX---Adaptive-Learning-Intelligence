from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class GoalProgress(BaseModel):
    """Today's progress toward the daily goal (FR-ENG-03)."""

    daily_goal: int
    today_valid: int  # valid answers today, in the student's time zone
    goal_met_today: bool
    just_met: bool = False  # true only on the answer that reached the goal
    current_streak: int


class StreakOut(GoalProgress):
    longest_streak: int
    today: date
    timezone: str


class ConceptChange(BaseModel):
    concept: str
    name: str
    before: float
    after: float


class WeeklyOut(BaseModel):
    """FR-ENG-05. Null (never a placeholder) when there's no data."""

    subject: str
    start: date
    end: date
    questions: int
    accuracy: float | None
    goal_days_met: int
    mean_mastery_start: float | None  # over concepts with an estimate at both times
    mean_mastery_end: float | None
    mastery_change: float | None
    concepts_improved: list[ConceptChange]


FeedbackCategory = Literal["bug", "content", "idea", "other"]


class FeedbackRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    category: FeedbackCategory
    message: str = Field(default="", max_length=2000)
    page: str | None = Field(default=None, max_length=200)


class FeedbackOut(BaseModel):
    id: int
