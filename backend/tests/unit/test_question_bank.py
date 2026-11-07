"""The real question bank must always be valid, and the validator must catch bad data."""

import pytest
from pydantic import ValidationError

from app.content.question_bank import (
    QUESTION_BANK_DIR,
    QuestionBank,
    load_question_bank,
)

SUBJECT_DIRS = sorted(p for p in QUESTION_BANK_DIR.iterdir() if p.is_dir())


@pytest.mark.parametrize("subject_dir", SUBJECT_DIRS, ids=lambda p: p.name)
def test_repository_question_bank_is_valid(subject_dir):
    bank = load_question_bank(subject_dir)
    assert bank.concepts, "subject has no concepts"
    order = bank.topological_order()
    position = {code: i for i, code in enumerate(order)}
    for c in bank.concepts:
        for pre in c.prerequisites:
            assert position[pre] < position[c.code]


@pytest.mark.parametrize("subject_dir", SUBJECT_DIRS, ids=lambda p: p.name)
def test_repository_question_bank_meets_coverage_standard(subject_dir):
    bank = load_question_bank(subject_dir)
    assert bank.coverage_problems() == []


def _bank(concepts, questions=()):
    return {
        "subject": {"code": "T", "name": "Test"},
        "concepts": concepts,
        "questions": list(questions),
    }


def _concept(code, prereqs=()):
    return {"code": code, "name": code, "description": "d", "prerequisites": list(prereqs)}


def _question(**overrides):
    q = {
        "id": "t-001",
        "concept": "t.a",
        "difficulty": 1,
        "stem": "What is the answer here?",
        "options": {"A": "one", "B": "two", "C": "three", "D": "four"},
        "answer": "A",
        "explanation": "Because one is the correct option.",
    }
    q.update(overrides)
    return q


def test_cycle_is_rejected():
    with pytest.raises(ValidationError, match="cycle"):
        QuestionBank(**_bank([_concept("t.a", ["t.b"]), _concept("t.b", ["t.a"])]))


def test_unknown_prerequisite_is_rejected():
    with pytest.raises(ValidationError, match="unknown prerequisites"):
        QuestionBank(**_bank([_concept("t.a", ["t.missing"])]))


def test_question_with_unknown_concept_is_rejected():
    with pytest.raises(ValidationError, match="unknown concept"):
        QuestionBank(**_bank([_concept("t.a")], [_question(concept="t.zzz")]))


def test_duplicate_question_ids_are_rejected():
    with pytest.raises(ValidationError, match="duplicate question ids"):
        QuestionBank(**_bank([_concept("t.a")], [_question(), _question()]))


def test_options_must_be_exactly_four_and_distinct():
    with pytest.raises(ValidationError):
        QuestionBank(**_bank([_concept("t.a")], [_question(options={"A": "x", "B": "y"})]))
    with pytest.raises(ValidationError, match="distinct"):
        QuestionBank(
            **_bank(
                [_concept("t.a")],
                [_question(options={"A": "x", "B": "x", "C": "y", "D": "z"})],
            )
        )


def test_question_cannot_be_diagnostic_and_test_form():
    with pytest.raises(ValidationError, match="both diagnostic and a test form"):
        QuestionBank(**_bank([_concept("t.a")], [_question(diagnostic=True, test_form="A")]))


def test_unknown_question_field_is_rejected():
    # Catches typos such as "diagnositc: true" that would otherwise be silently ignored.
    with pytest.raises(ValidationError):
        QuestionBank(**_bank([_concept("t.a")], [_question(diagnositc=True)]))


def test_duplicate_stems_are_rejected():
    with pytest.raises(ValidationError, match="duplicate question stems"):
        QuestionBank(**_bank([_concept("t.a")], [_question(id="t-001"), _question(id="t-002")]))


def test_non_string_option_is_rejected():
    # YAML turns bare yes/no into booleans; they must be quoted.
    opts = {"A": True, "B": "two", "C": "three", "D": "four"}
    with pytest.raises(ValidationError):
        QuestionBank(**_bank([_concept("t.a")], [_question(options=opts)]))


def _full_concept_questions(prefix, answers):
    """15 questions for one concept: diagnostic, 12 practice, form A, form B."""
    kinds = (
        [{"diagnostic": True, "difficulty": 2}]
        + [{"difficulty": d} for d in (1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3)]
        + [{"test_form": "A", "difficulty": 2}, {"test_form": "B", "difficulty": 2}]
    )
    return [
        _question(id=f"{prefix}-{i:03d}", stem=f"Question number {i} here?", answer=a, **k)
        for i, (k, a) in enumerate(zip(kinds, answers, strict=True), start=1)
    ]


def test_coverage_standard_passes_for_complete_balanced_concept():
    answers = list("ABCDABCDABCDABC")
    bank = QuestionBank(**_bank([_concept("t.a")], _full_concept_questions("t", answers)))
    problems = bank.coverage_problems()
    # With a single concept, each fixed test has one question, so its letter share is
    # 100% by construction; only the per-concept rules are checked here.
    assert [p for p in problems if not p.startswith(("diagnostic", "form"))] == []


def test_coverage_reports_missing_diagnostic_and_forms():
    bank = QuestionBank(**_bank([_concept("t.a")], [_question()]))
    problems = " ".join(bank.coverage_problems())
    assert "exactly 1 diagnostic" in problems
    assert "form-A" in problems
    assert "form-B" in problems
    assert "practice questions" in problems


def test_coverage_reports_skewed_answer_letters():
    answers = ["A"] * 15
    bank = QuestionBank(**_bank([_concept("t.a")], _full_concept_questions("t", answers)))
    assert any("all questions: answer A" in p for p in bank.coverage_problems())
