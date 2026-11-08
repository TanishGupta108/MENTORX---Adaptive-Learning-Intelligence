from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

TestStatus = Literal["unavailable", "todo", "in_progress", "done"]


class TestState(BaseModel):
    status: TestStatus
    session_id: uuid.UUID | None = None  # the active session, to resume
    questions: int  # number of questions in the form


class PilotStatus(BaseModel):
    """What the study asks of this student next. Never reveals the experiment group."""

    pilot_active: bool
    in_study: bool  # assigned at sign-up while the pilot was running
    consented: bool
    pretest: TestState
    posttest: TestState
    sus_done: bool


class SusRequest(BaseModel):
    # The 10 standard SUS items, each answered 1 (strongly disagree) to 5 (strongly agree).
    answers: list[int] = Field(min_length=10, max_length=10)
    comment: str = Field(default="", max_length=2000)


class SusOut(BaseModel):
    score: float


# ---------------------------------------------------------------- admin


class GroupOutcome(BaseModel):
    group: str
    participants: int  # consenting students in this group
    pretest_done: int
    posttest_done: int
    mean_pre: float | None  # fraction correct, 0-1
    mean_post: float | None
    mean_gain: float | None  # over students with both tests
    gain_ci95: tuple[float, float] | None
    sus_n: int
    sus_mean: float | None


class CalibrationBin(BaseModel):
    lo: float
    hi: float
    n: int
    mean_predicted: float
    observed: float


class ModelQuality(BaseModel):
    n: int  # answers with a stored prediction
    auc: float | None
    brier: float | None
    ece: float | None  # expected calibration error
    bins: list[CalibrationBin]


class Engagement(BaseModel):
    students: int
    wau: int  # students with an answer in the last 7 days
    d1_retention: float | None  # of students who signed up 1+ days ago: active on day 1
    d7_retention: float | None  # of students who signed up 7+ days ago: active on day 7
    sessions_started: int
    completion_rate: float | None


class FeedbackSummary(BaseModel):
    n: int
    mean_rating: float | None
    recent: list[dict]


class PilotMetrics(BaseModel):
    """FR-DASH-09. Research outcomes use consenting participants only."""

    pilot_active: bool
    posttest_open: bool
    groups: list[GroupOutcome]
    gain_difference: float | None  # adaptive minus control mean gain
    gain_difference_ci95: tuple[float, float] | None
    cohens_d: float | None
    engagement: Engagement
    model: ModelQuality
    feedback: FeedbackSummary
