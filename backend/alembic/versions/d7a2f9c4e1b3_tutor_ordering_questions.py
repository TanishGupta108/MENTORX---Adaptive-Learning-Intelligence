"""tutor: ordering questions (answer_type 'ordering')

Revision ID: d7a2f9c4e1b3
Revises: c5e8a1f4b2d7
Create Date: 2026-11-14 10:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d7a2f9c4e1b3"
down_revision: str | None = "c5e8a1f4b2d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TYPES = (
    "'numeric', 'multiple_choice', 'check_all', 'algebraic', "
    "'numeric_expression', 'exact_fraction', 'exact_match', 'other'"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_items_answer_type"), "items", type_="check")
    op.create_check_constraint(
        op.f("ck_items_answer_type"), "items", f"answer_type IN ({TYPES}, 'ordering')"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE items SET answer_type = 'other', "
        "exclusion_reason = 'unsupported_answer_type: Ordering' WHERE answer_type = 'ordering'"
    )
    op.drop_constraint(op.f("ck_items_answer_type"), "items", type_="check")
    op.create_check_constraint(op.f("ck_items_answer_type"), "items", f"answer_type IN ({TYPES})")
