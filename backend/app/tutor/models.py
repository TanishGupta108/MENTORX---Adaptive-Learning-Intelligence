"""Tables for the adaptive tutor (MENTORX v2: Mathematics on FoundationalASSIST).

Design rules:
- Content (skills, items, resources) is keyed by the dataset's own IDs where they exist, so
  model indices and admin edits always refer to the same thing.
- `interactions` is the raw, append-only answer log. `skill_states` is DERIVED from it (plus
  model predictions) and can be rebuilt at any time.
- Answer keys live only in `items.answer_key` and are never serialised to the client.
- Generic column types (JSON, Uuid) keep these tables portable beyond PostgreSQL.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _user_fk() -> ForeignKey:
    return ForeignKey("users.id", ondelete="CASCADE")


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


STATUSES = ("likely_strength", "developing", "potential_weakness", "needs_assessment")
MODES = ("foundation", "guided", "independent", "advanced")
DIFFICULTIES = ("easy", "medium", "hard", "unrated")


# ---------------------------------------------------------------- content


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # dataset skill_id
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)  # Common Core code, e.g. 7.RP.A.3
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    grade: Mapped[int | None] = mapped_column(SmallInteger)
    domain_code: Mapped[str] = mapped_column(String(10), nullable=False)
    domain_name: Mapped[str] = mapped_column(String(80), nullable=False)
    standard_url: Mapped[str | None] = mapped_column(String(200))
    n_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    model_supported: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class SkillPrerequisite(Base):
    """Curated prerequisite links only. Never inferred from a student's poor performance."""

    __tablename__ = "skill_prerequisites"
    __table_args__ = (CheckConstraint("skill_id <> prerequisite_id", name="not_self"),)

    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    prerequisite_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(200), nullable=False)


class Item(Base):
    """One dataset question. Excluded items are kept (with the reason) for transparency."""

    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint(
            "answer_type IN ('numeric', 'multiple_choice', 'check_all', 'algebraic', "
            "'numeric_expression', 'exact_fraction', 'exact_match', 'ordering', 'other')",
            name="answer_type",
        ),
        CheckConstraint("difficulty IN ('easy', 'medium', 'hard', 'unrated')", name="difficulty"),
        Index("ix_items_skill_usable", "skill_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # dataset problem_id
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False
    )
    body_html: Mapped[str] = mapped_column(Text, nullable=False)  # sanitised
    answer_type: Mapped[str] = mapped_column(String(20), nullable=False)
    options: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # [{"id", "html"}]
    # SERVER ONLY. A list for numeric/choice questions, {"alts", "form"} for typed answers.
    answer_key: Mapped[list | dict] = mapped_column(JSON, nullable=False, default=list)
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False, server_default="unrated")
    success_rate: Mapped[float | None] = mapped_column(Float)  # training students only
    train_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    n_skills: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    problem_set: Mapped[str] = mapped_column(String(40), nullable=False, server_default="")
    exclusion_reason: Mapped[str | None] = mapped_column(String(80))  # None = usable
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Extra rendering data for non-text questions, e.g. Geography maps: {"kind": "map", "map",
    # "regions": [{"label", "d", "anchor", "shape"}]}. Never contains the answer (no place codes).
    media: Mapped[dict | None] = mapped_column(JSON)

    @property
    def usable(self) -> bool:
        return self.is_active and self.exclusion_reason is None


class ItemSkill(Base):
    """The dataset's full question-to-skill mapping (including multi-skill questions)."""

    __tablename__ = "item_skills"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )


class Resource(Base):
    __tablename__ = "learning_resources"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('notes', 'worked_example', 'standard', 'video', 'article', 'practice_tip')",
            name="kind",
        ),
        CheckConstraint("url IS NOT NULL OR content_md IS NOT NULL", name="has_content"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int | None] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    url: Mapped[str | None] = mapped_column(String(500))
    content_md: Mapped[str | None] = mapped_column(Text)
    minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="5")
    source_label: Mapped[str] = mapped_column(String(120), nullable=False)
    is_original: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    seed_key: Mapped[str | None] = mapped_column(String(120), unique=True)  # for idempotent seeding
    created_at: Mapped[datetime] = _created()


# ---------------------------------------------------------------- students


class StudentProfile(Base):
    __tablename__ = "student_profiles"
    __table_args__ = (
        CheckConstraint(
            "goal_type IS NULL OR goal_type IN ('assess_overall', 'improve_weak', 'learn_topic')",
            name="goal_type",
        ),
        CheckConstraint(
            "pace_preference IN ('more_support', 'balanced', 'challenge')", name="pace_preference"
        ),
        CheckConstraint("daily_goal BETWEEN 1 AND 200", name="daily_goal"),
        CheckConstraint("grade IS NULL OR grade BETWEEN 3 AND 8", name="grade"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, _user_fk(), primary_key=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"))
    goal_type: Mapped[str | None] = mapped_column(String(20))
    focus_skill_id: Mapped[int | None] = mapped_column(ForeignKey("skills.id", ondelete="SET NULL"))
    pace_preference: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="balanced"
    )
    hints_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    daily_goal: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="10")
    grade: Mapped[int | None] = mapped_column(SmallInteger)  # school grade 3-8; None = not sure
    pace_suggestion_dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    diagnostic_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_skill_id: Mapped[int | None] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created()


class LearningGoal(Base):
    __tablename__ = "learning_goals"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('strengthen_skills', 'weekly_practice', 'master_skill')", name="kind"
        ),
        CheckConstraint("target BETWEEN 1 AND 500", name="target"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, _user_fk(), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    target: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    skill_id: Mapped[int | None] = mapped_column(ForeignKey("skills.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    achieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint("kind IN ('diagnostic', 'skill_check', 'reassessment')", name="kind"),
        CheckConstraint("status IN ('active', 'completed', 'abandoned')", name="status"),
        Index("ix_assessments_user_started", "user_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, _user_fk(), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    skill_id: Mapped[int | None] = mapped_column(ForeignKey("skills.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="active")
    planned_item_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    answered_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    correct_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    current_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"))
    current_served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_predicted_p: Mapped[float | None] = mapped_column(Float)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Adaptive diagnostic: questions are chosen one at a time, so the length is stored here
    # and planned_item_ids grows as questions are served. Other kinds plan everything upfront.
    target_n: Mapped[int | None] = mapped_column(SmallInteger)
    started_at: Mapped[datetime] = _created()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def target_count(self) -> int:
        return self.target_n or len(self.planned_item_ids)


class PracticeSession(Base):
    __tablename__ = "practice_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'completed', 'abandoned')", name="status"),
        CheckConstraint("difficulty IN ('easy', 'medium', 'hard')", name="difficulty"),
        CheckConstraint("mode IN ('foundation', 'guided', 'independent', 'advanced')", name="mode"),
        CheckConstraint("kind IN ('skill', 'mixed', 'review')", name="kind"),
        CheckConstraint("(kind = 'skill') = (skill_id IS NOT NULL)", name="skill_kind_has_skill"),
        Index("ix_practice_sessions_user_started", "user_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, _user_fk(), nullable=False)
    # 'skill': one skill (single-skill questions). 'mixed': multi-skill questions across
    # the skills the student has worked on (skill_id is NULL). 'review': spaced review of the
    # skills that are due, interleaved (skill_id is NULL; the plan holds skills and items).
    kind: Mapped[str] = mapped_column(String(8), nullable=False, server_default="skill")
    skill_id: Mapped[int | None] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    guided: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="active")
    target_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    answered_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    correct_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    recent: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # 1/0 in this session
    current_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"))
    current_served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_predicted_p: Mapped[float | None] = mapped_column(Float)
    current_hint_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    current_selection: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # review sessions: {"skills": [ids], "items": [ids in serving order]}; null otherwise
    plan: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = _created()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Interaction(Base):
    """Raw, append-only answer log. Never updated."""

    __tablename__ = "interactions"
    __table_args__ = (
        CheckConstraint("context IN ('assessment', 'practice')", name="context"),
        UniqueConstraint("assessment_id", "item_id", name="uq_interactions_assessment_item"),
        UniqueConstraint("practice_id", "item_id", name="uq_interactions_practice_item"),
        Index("ix_interactions_user_created", "user_id", "created_at"),
        Index("ix_interactions_user_skill", "user_id", "skill_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, _user_fk(), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)  # primary skill
    # >1 = a multi-skill question: never counted as per-skill evidence (one shared score),
    # but given to the model with all its skills.
    n_skills: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    context: Mapped[str] = mapped_column(String(12), nullable=False)
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("assessments.id", ondelete="CASCADE")
    )
    practice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("practice_sessions.id", ondelete="CASCADE")
    )
    response: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hint_used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    saw_answer: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # The model's label: correct on the first try with no hint and no answer shown.
    model_label: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_ms: Mapped[int | None] = mapped_column(Integer)
    predicted_p: Mapped[float | None] = mapped_column(Float)  # stored BEFORE the answer
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False, server_default="unrated")
    created_at: Mapped[datetime] = _created()


class SkillState(Base):
    """Latest derived estimate per student and skill (rebuildable from interactions)."""

    __tablename__ = "skill_states"
    __table_args__ = (
        CheckConstraint(
            "status IN ('likely_strength', 'developing', 'potential_weakness', 'needs_assessment')",
            name="status",
        ),
        CheckConstraint("evidence IN ('none', 'limited', 'moderate', 'strong')", name="evidence"),
        CheckConstraint("mode IN ('foundation', 'guided', 'independent', 'advanced')", name="mode"),
        CheckConstraint(
            "mode_override IS NULL OR mode_override IN ('foundation', 'guided', 'independent', 'advanced')",
            name="mode_override",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, _user_fk(), primary_key=True)
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    correct: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    hints_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    recent: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # last 10 is_correct
    predicted_p: Mapped[float | None] = mapped_column(Float)  # model, mean over the skill's items
    model_name: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="needs_assessment"
    )
    evidence: Mapped[str] = mapped_column(String(10), nullable=False, server_default="none")
    mode: Mapped[str] = mapped_column(String(12), nullable=False, server_default="guided")
    mode_override: Mapped[str | None] = mapped_column(String(12))
    reassessed_accuracy: Mapped[float | None] = mapped_column(Float)
    # first time the mastery rule held (observed answers only); "stuck" needs it to be unset
    mastered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # spaced review: 0 = first review; each successful review moves one step further along
    # REVIEW_INTERVALS (3, 7, 14, 30, 60 days)
    revision_stage: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = _created()


class ResourceCompletion(Base):
    __tablename__ = "resource_completions"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, _user_fk(), primary_key=True)
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("learning_resources.id", ondelete="CASCADE"), primary_key=True
    )
    completed_at: Mapped[datetime] = _created()


class Recommendation(Base):
    """A generated recommendation, with its reason. The current set is the learning path."""

    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(
            "reason_code IN ('weakness', 'developing', 'needs_assessment', 'revision', "
            "'prerequisite', 'next_objective', 'focus', 'stuck', 'review')",
            name="reason_code",
        ),
        Index("ix_recommendations_user_current", "user_id", "is_current"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, _user_fk(), nullable=False)
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    activities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _created()


class AiExplanation(Base):
    """Cached AI tutor text (an explanation of a question, or a hint that must not give the
    answer away). Generated once per question (and, for explanations, per wrong answer),
    clearly labelled as AI-generated, and hideable by admins."""

    __tablename__ = "ai_explanations"
    __table_args__ = (
        CheckConstraint("kind IN ('explanation', 'hint')", name="kind"),
        CheckConstraint("status IN ('ok', 'hidden')", name="status"),
        UniqueConstraint("item_id", "kind", "answer_sig", name="uq_ai_explanations_item_kind_sig"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    answer_sig: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, server_default="ok")
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created()
