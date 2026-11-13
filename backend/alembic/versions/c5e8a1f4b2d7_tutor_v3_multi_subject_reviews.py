"""tutor v3: multi-subject, grade, pace suggestion, map media, review sessions

Revision ID: c5e8a1f4b2d7
Revises: 3a3323760dc2
Create Date: 2026-11-13 12:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5e8a1f4b2d7"
down_revision: str | None = "3a3323760dc2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_REASONS = (
    "reason_code IN ('weakness', 'developing', 'needs_assessment', 'revision', "
    "'prerequisite', 'next_objective', 'focus')"
)
NEW_REASONS = (
    "reason_code IN ('weakness', 'developing', 'needs_assessment', 'revision', "
    "'prerequisite', 'next_objective', 'focus', 'stuck', 'review')"
)


def upgrade() -> None:
    op.add_column("student_profiles", sa.Column("grade", sa.SmallInteger(), nullable=True))
    op.add_column(
        "student_profiles",
        sa.Column("pace_suggestion_dismissed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_student_profiles_grade"),
        "student_profiles",
        "grade IS NULL OR grade BETWEEN 3 AND 8",
    )
    op.add_column("items", sa.Column("media", sa.JSON(), nullable=True))
    op.add_column("practice_sessions", sa.Column("plan", sa.JSON(), nullable=True))
    # Every mixed session before v3 was Mathematics: record that, so subject scoping
    # (activity, Progress history, resuming) files them correctly.
    op.execute(
        """
        UPDATE practice_sessions
        SET plan = json_build_object('subject_id', (SELECT id FROM subjects WHERE code = 'MATH'))
        WHERE kind = 'mixed' AND plan IS NULL
          AND EXISTS (SELECT 1 FROM subjects WHERE code = 'MATH')
        """
    )
    op.add_column(
        "skill_states", sa.Column("mastered_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.drop_constraint(
        op.f("ck_practice_sessions_mixed_has_no_skill"), "practice_sessions", type_="check"
    )
    op.drop_constraint(op.f("ck_practice_sessions_kind"), "practice_sessions", type_="check")
    op.create_check_constraint(
        op.f("ck_practice_sessions_kind"),
        "practice_sessions",
        "kind IN ('skill', 'mixed', 'review')",
    )
    op.create_check_constraint(
        op.f("ck_practice_sessions_skill_kind_has_skill"),
        "practice_sessions",
        "(kind = 'skill') = (skill_id IS NOT NULL)",
    )

    op.drop_constraint(op.f("ck_recommendations_reason_code"), "recommendations", type_="check")
    op.create_check_constraint(
        op.f("ck_recommendations_reason_code"), "recommendations", NEW_REASONS
    )

    # Per-subject diagnostic flag: Enrollment is now the source of truth.
    op.execute(
        """
        INSERT INTO enrollments (user_id, subject_id, enrolled_at)
        SELECT p.user_id, p.subject_id, now()
        FROM student_profiles p
        WHERE p.subject_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM enrollments e
            WHERE e.user_id = p.user_id AND e.subject_id = p.subject_id
          )
        """
    )
    op.execute(
        """
        UPDATE enrollments e
        SET diagnostic_completed_at = p.diagnostic_completed_at
        FROM student_profiles p
        WHERE e.user_id = p.user_id
          AND e.subject_id = p.subject_id
          AND e.diagnostic_completed_at IS NULL
          AND p.diagnostic_completed_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM recommendations WHERE reason_code IN ('stuck', 'review')")
    op.drop_constraint(op.f("ck_recommendations_reason_code"), "recommendations", type_="check")
    op.create_check_constraint(
        op.f("ck_recommendations_reason_code"), "recommendations", OLD_REASONS
    )

    # Keep the answers of review sessions (interactions cascade on delete): they become
    # mixed sessions, which the old check allows (no skill).
    op.execute("UPDATE practice_sessions SET kind = 'mixed' WHERE kind = 'review'")
    op.drop_constraint(
        op.f("ck_practice_sessions_skill_kind_has_skill"), "practice_sessions", type_="check"
    )
    op.drop_constraint(op.f("ck_practice_sessions_kind"), "practice_sessions", type_="check")
    op.create_check_constraint(
        op.f("ck_practice_sessions_kind"), "practice_sessions", "kind IN ('skill', 'mixed')"
    )
    op.create_check_constraint(
        op.f("ck_practice_sessions_mixed_has_no_skill"),
        "practice_sessions",
        "(kind = 'mixed') = (skill_id IS NULL)",
    )
    op.drop_column("skill_states", "mastered_at")
    op.drop_column("practice_sessions", "plan")
    op.drop_column("items", "media")
    op.drop_constraint(op.f("ck_student_profiles_grade"), "student_profiles", type_="check")
    op.drop_column("student_profiles", "pace_suggestion_dismissed_at")
    op.drop_column("student_profiles", "grade")
    # enrollments.diagnostic_completed_at already existed; the backfilled values are harmless.
