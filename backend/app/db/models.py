"""SQLAlchemy models. Authoritative description: docs/design/database.md.

Conventions: UUID keys for user-owned rows (not guessable), integer keys for content.
Every table that belongs to a user cascades on user delete, so account deletion
(FR-AUTH-11) is a single DELETE.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def user_fk() -> ForeignKey:
    return ForeignKey("users.id", ondelete="CASCADE")


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------- users & auth


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('student', 'admin')", name="role"),
        CheckConstraint("daily_goal BETWEEN 1 AND 100", name="daily_goal"),
        CheckConstraint(
            "experiment_group IS NULL OR experiment_group IN ('adaptive', 'control')",
            name="experiment_group",
        ),
        CheckConstraint("pretest_form IS NULL OR pretest_form IN ('A', 'B')", name="pretest_form"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="student")
    consent_research: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    privacy_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    daily_goal: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="10")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Asia/Kolkata")
    experiment_group: Mapped[str | None] = mapped_column(String(10))
    pretest_form: Mapped[str | None] = mapped_column(String(1))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    enrollments: Mapped[list[Enrollment]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), user_fk(), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _now()


# ---------------------------------------------------------------- content


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    concepts: Mapped[list[Concept]] = relationship(back_populates="subject")


class Enrollment(Base):
    __tablename__ = "enrollments"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), user_fk(), primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True
    )
    enrolled_at: Mapped[datetime] = _now()
    diagnostic_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="enrollments")
    subject: Mapped[Subject] = relationship()


class ConceptPrerequisite(Base):
    __tablename__ = "concept_prerequisites"
    __table_args__ = (CheckConstraint("concept_id <> prerequisite_id", name="not_self"),)

    concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True
    )
    prerequisite_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True
    )


class Concept(Base):
    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    topo_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    subject: Mapped[Subject] = relationship(back_populates="concepts")
    prerequisites: Mapped[list[Concept]] = relationship(
        secondary="concept_prerequisites",
        primaryjoin="Concept.id == ConceptPrerequisite.concept_id",
        secondaryjoin="Concept.id == ConceptPrerequisite.prerequisite_id",
        viewonly=True,
    )


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("external_id", "version", name="uq_questions_external_id_version"),
        CheckConstraint("author_difficulty BETWEEN 1 AND 3", name="author_difficulty"),
        CheckConstraint("correct_key IN ('A', 'B', 'C', 'D')", name="correct_key"),
        CheckConstraint("jsonb_array_length(options) = 4", name="four_options"),
        CheckConstraint("status IN ('active', 'retired')", name="status"),
        CheckConstraint("test_form IS NULL OR test_form IN ('A', 'B')", name="test_form"),
        CheckConstraint("NOT (is_diagnostic AND test_form IS NOT NULL)", name="diag_or_form"),
        # Only one active version per question.
        Index(
            "uq_questions_active_external_id",
            "external_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_questions_concept_status", "concept_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id", ondelete="RESTRICT"), nullable=False
    )
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSONB, nullable=False)  # [{"key": "A", "text": "..."}]
    correct_key: Mapped[str] = mapped_column(String(1), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    author_difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    est_difficulty: Mapped[float | None] = mapped_column(Float)
    is_diagnostic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    test_form: Mapped[str | None] = mapped_column(String(1))
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    # SHA-256 of the content fields; the seed command uses it to detect edits (FR-CONT-06).
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = _now()

    concept: Mapped[Concept] = relationship()


# ---------------------------------------------------------------- learning activity


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        CheckConstraint("model_type IN ('gbm', 'logreg', 'bkt', 'prior')", name="model_type"),
        Index(
            "uq_model_versions_active", "is_active", unique=True, postgresql_where=text("is_active")
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    model_type: Mapped[str] = mapped_column(String(10), nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(String(300))
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    feature_names: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    training_data: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


class StudySession(Base):
    __tablename__ = "study_sessions"
    __table_args__ = (
        CheckConstraint(
            "type IN ('diagnostic', 'practice', 'revision', 'pretest', 'posttest', 'challenge')",
            name="type",
        ),
        CheckConstraint("status IN ('active', 'completed', 'abandoned')", name="status"),
        Index("ix_study_sessions_user_started", "user_id", text("started_at DESC")),
        Index(
            "uq_study_sessions_one_active",
            "user_id",
            "subject_id",
            "type",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), user_fk(), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(12), nullable=False)
    focus_concept_id: Mapped[int | None] = mapped_column(ForeignKey("concepts.id"))
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    target_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    answered_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    current_question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"))
    current_served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_predicted_p: Mapped[float | None] = mapped_column(Float)
    current_model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"))
    started_at: Mapped[datetime] = _now()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Attempt(Base):
    """Raw, append-only record of one answer. Never updated."""

    __tablename__ = "attempts"
    __table_args__ = (
        CheckConstraint(
            "selected_key IS NULL OR selected_key IN ('A', 'B', 'C', 'D')", name="selected_key"
        ),
        CheckConstraint("response_ms IS NULL OR response_ms >= 0", name="response_ms"),
        Index("ix_attempts_user_created", "user_id", "created_at"),
        Index("ix_attempts_user_question", "user_id", "question_id"),
        Index("ix_attempts_session", "session_id"),
        Index("ix_attempts_question", "question_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), user_fk(), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("study_sessions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), nullable=False)
    selected_key: Mapped[str | None] = mapped_column(String(1))
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_ms: Mapped[int | None] = mapped_column(Integer)
    attempt_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    predicted_p_correct: Mapped[float | None] = mapped_column(Float)
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"))
    created_at: Mapped[datetime] = _now()


class Mastery(Base):
    """Derived: can be rebuilt from attempts at any time."""

    __tablename__ = "mastery"
    __table_args__ = (
        CheckConstraint("p_mastery BETWEEN 0 AND 1", name="p_mastery"),
        CheckConstraint("peak_mastery BETWEEN 0 AND 1", name="peak_mastery"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), user_fk(), primary_key=True)
    concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True
    )
    p_mastery: Mapped[float] = mapped_column(Float, nullable=False)
    peak_mastery: Mapped[float] = mapped_column(Float, nullable=False)
    n_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"), nullable=False)
    updated_at: Mapped[datetime] = _now()


class MasterySnapshot(Base):
    __tablename__ = "mastery_snapshots"
    __table_args__ = (
        Index("ix_mastery_snapshots_user_concept_time", "user_id", "concept_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), user_fk(), nullable=False)
    concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False
    )
    p_mastery: Mapped[float] = mapped_column(Float, nullable=False)
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = _now()


class LearningPath(Base):
    __tablename__ = "learning_paths"
    __table_args__ = (
        CheckConstraint(
            "trigger IN ('diagnostic', 'session', 'revision', 'manual')", name="trigger"
        ),
        Index(
            "uq_learning_paths_one_current",
            "user_id",
            "subject_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), user_fk(), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    trigger: Mapped[str] = mapped_column(String(12), nullable=False)
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"))
    generated_at: Mapped[datetime] = _now()


class LearningPathItem(Base):
    __tablename__ = "learning_path_items"
    __table_args__ = (
        CheckConstraint("reason IN ('weak', 'prerequisite', 'revision', 'new')", name="reason"),
        CheckConstraint("target_difficulty BETWEEN 1 AND 3", name="target_difficulty"),
    )

    path_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_paths.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(12), nullable=False)
    target_difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    mastery_at_generation: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)


class GoalDay(Base):
    """A local day on which the student reached their daily goal (FR-ENG-01).

    Stores the goal in force at that moment, so later goal changes don't rewrite history.
    """

    __tablename__ = "goal_days"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), user_fk(), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    goal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    met_at: Mapped[datetime] = _now()


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="rating"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), user_fk())
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    page: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = _now()


class QuestionFlag(Base):
    __tablename__ = "question_flags"
    __table_args__ = (CheckConstraint("status IN ('open', 'resolved')", name="status"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), user_fk(), nullable=False)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="open")
    created_at: Mapped[datetime] = _now()
