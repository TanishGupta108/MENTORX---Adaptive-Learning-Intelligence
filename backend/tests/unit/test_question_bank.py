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
