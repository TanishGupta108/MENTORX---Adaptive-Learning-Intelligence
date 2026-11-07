"""FR-CONT-03..07: the seed command is idempotent and versions edited questions."""

from sqlalchemy import func, select

from app.content.question_bank import QUESTION_BANK_DIR, QuestionBank, load_question_bank
from app.content.seed import seed
from app.db.models import ConceptPrerequisite, Question


def _bank() -> QuestionBank:
    return load_question_bank(QUESTION_BANK_DIR / "machine_learning")


def _active(db) -> int:
    return db.scalar(select(func.count()).select_from(Question).where(Question.status == "active"))


def test_seed_loads_everything_and_is_idempotent(db):
    first = seed(db, _bank(), include_drafts=True)
    assert first.questions_created == 285 and first.concepts_created == 19
    second = seed(db, _bank(), include_drafts=True)
    assert second.questions_created == second.questions_versioned == second.questions_retired == 0
    assert second.questions_unchanged == 285
    assert _active(db) == 285
    assert db.scalar(select(func.count()).select_from(ConceptPrerequisite)) == sum(
        len(c.prerequisites) for c in _bank().concepts
    )


def test_editing_a_question_creates_a_new_version(db):
    seed(db, _bank(), include_drafts=True)
    bank = _bank()
    q = bank.questions[0]
    q.stem = q.stem + " (edited)"
    report = seed(db, bank, include_drafts=True)
    assert report.questions_versioned == 1
    rows = db.scalars(
        select(Question).where(Question.external_id == q.id).order_by(Question.version)
    ).all()
    assert [(r.version, r.status) for r in rows] == [(1, "retired"), (2, "active")]
    assert rows[1].stem.endswith("(edited)")


def test_removed_question_is_retired_not_deleted(db):
    seed(db, _bank(), include_drafts=True)
    bank = _bank()
    removed = bank.questions.pop()
    report = seed(db, bank, include_drafts=True)
    assert report.questions_retired == 1
    row = db.scalar(select(Question).where(Question.external_id == removed.id))
    assert row.status == "retired"


def test_reviewed_only_mode_skips_drafts(db):
    bank = _bank()
    bank.questions[0].review_status = "reviewed"
    report = seed(db, bank, include_drafts=False)
    assert report.drafts_skipped == len(bank.questions) - 1
    assert _active(db) == 1


def test_options_are_stored_in_key_order_and_answer_is_kept_server_side(db):
    seed(db, _bank(), include_drafts=True)
    q = db.scalar(select(Question).where(Question.external_id == "found-001"))
    assert [o["key"] for o in q.options] == ["A", "B", "C", "D"]
    assert q.correct_key == "A"
