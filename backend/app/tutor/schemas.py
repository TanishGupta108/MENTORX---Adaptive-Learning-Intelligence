"""Request bodies for the tutor API (responses are plain JSON built in views/services)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

GoalType = Literal["assess_overall", "improve_weak", "learn_topic"]
GoalKind = Literal["strengthen_skills", "weekly_practice", "master_skill"]
Mode = Literal["foundation", "guided", "independent", "advanced"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OnboardingRequest(Strict):
    goal_type: GoalType
    focus_skill_id: int | None = None
    goal_kind: GoalKind = "strengthen_skills"
    goal_target: int | None = Field(default=None, ge=1, le=500)

    @model_validator(mode="after")
    def topic_needs_skill(self) -> OnboardingRequest:
        if self.goal_type == "learn_topic" and self.focus_skill_id is None:
            raise ValueError("choose the topic you want to learn")
        if self.goal_kind == "master_skill" and self.focus_skill_id is None:
            raise ValueError("choose the topic you want to master")
        return self


class ProfileUpdate(Strict):
    pace_preference: Literal["more_support", "balanced", "challenge"] | None = None
    hints_enabled: bool | None = None
    goal_type: GoalType | None = None
    focus_skill_id: int | None = None
    daily_goal: int | None = Field(default=None, ge=1, le=200)  # questions per day


class GoalRequest(Strict):
    kind: GoalKind
    target: int | None = Field(default=None, ge=1, le=500)
    skill_id: int | None = None


class ModeRequest(Strict):
    mode: Mode | None  # null = back to the automatic, evidence-based mode


class StartAssessment(Strict):
    kind: Literal["diagnostic", "skill_check", "reassessment"]
    skill_id: int | None = None

    @model_validator(mode="after")
    def skill_for_skill_kinds(self) -> StartAssessment:
        if self.kind != "diagnostic" and self.skill_id is None:
            raise ValueError("skill_id is required for a skill check or reassessment")
        return self


class AnswerRequest(Strict):
    item_id: int
    value: str | None = Field(default=None, max_length=60)  # numeric or typed answer
    choice: str | None = Field(default=None, max_length=8)  # multiple choice
    choices: list[str] | None = Field(default=None, max_length=12)  # check all that apply

    def response(self) -> dict:
        return {
            k: v
            for k, v in (("value", self.value), ("choice", self.choice), ("choices", self.choices))
            if v is not None
        }


class StartPractice(Strict):
    kind: Literal["skill", "mixed"] = "skill"
    skill_id: int | None = None
    guided: bool = False

    @model_validator(mode="after")
    def skill_for_skill_practice(self) -> StartPractice:
        if self.kind == "skill" and self.skill_id is None:
            raise ValueError("skill_id is required for skill practice")
        return self


class ExplainRequest(Strict):
    interaction_id: int


class AiStatusUpdate(Strict):
    status: Literal["ok", "hidden"]


class PracticeAnswer(AnswerRequest):
    reveal: bool = False  # "show me the answer" (counts as not correct)


class CompletionRequest(Strict):
    completed: bool = True


class ResourceIn(Strict):
    skill_id: int | None = None
    kind: Literal["notes", "worked_example", "standard", "video", "article", "practice_tip"]
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=2000)
    url: str | None = Field(default=None, pattern=r"^https://[^\s]+$", max_length=500)
    content_md: str | None = Field(default=None, max_length=20000)
    minutes: int = Field(default=5, ge=1, le=240)
    source_label: str = Field(default="Added by an administrator", min_length=2, max_length=120)
    position: int = Field(default=20, ge=0, le=999)
    is_active: bool = True


class SkillDescription(Strict):
    description: str = Field(max_length=4000)


class ItemActive(Strict):
    is_active: bool


class PrerequisiteIn(Strict):
    skill_id: int
    prerequisite_id: int
