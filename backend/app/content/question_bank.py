"""Load and validate a subject's question bank from YAML.

Used by tests (so a bad question can never be merged) and, from M5, by the
seed script that loads questions into the database.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

OptionKey = Literal["A", "B", "C", "D"]

REPO_ROOT = Path(__file__).resolve().parents[3]
QUESTION_BANK_DIR = REPO_ROOT / "question_bank"


class QuestionBankError(ValueError):
    """Raised when the question bank breaks a rule."""


class SubjectSpec(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1)
    description: str = ""


class ConceptSpec(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$", max_length=40)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    prerequisites: list[str] = Field(default_factory=list)


class QuestionSpec(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9]+-\d{3,}$")
    concept: str
    difficulty: Literal[1, 2, 3]
    diagnostic: bool = False
    stem: str = Field(min_length=10)
    options: dict[OptionKey, str]
    answer: OptionKey
    explanation: str = Field(min_length=20)

    @field_validator("options")
    @classmethod
    def four_distinct_options(cls, v: dict[str, str]) -> dict[str, str]:
        if set(v) != {"A", "B", "C", "D"}:
            raise ValueError("options must have exactly the keys A, B, C, D")
        texts = [t.strip().lower() for t in v.values()]
        if any(not t for t in texts):
            raise ValueError("option text must not be empty")
        if len(set(texts)) != 4:
            raise ValueError("option texts must be distinct")
        return v


class QuestionBank(BaseModel):
    subject: SubjectSpec
    concepts: list[ConceptSpec]
    questions: list[QuestionSpec]

    @model_validator(mode="after")
    def check_integrity(self) -> QuestionBank:
        concept_codes = [c.code for c in self.concepts]
        dupes = [c for c, n in Counter(concept_codes).items() if n > 1]
        if dupes:
            raise QuestionBankError(f"duplicate concept codes: {dupes}")

        known = set(concept_codes)
        for c in self.concepts:
            unknown = set(c.prerequisites) - known
            if unknown:
                raise QuestionBankError(f"{c.code}: unknown prerequisites {sorted(unknown)}")
            if c.code in c.prerequisites:
                raise QuestionBankError(f"{c.code}: concept lists itself as a prerequisite")
        _assert_acyclic({c.code: c.prerequisites for c in self.concepts})

        q_dupes = [i for i, n in Counter(q.id for q in self.questions).items() if n > 1]
        if q_dupes:
            raise QuestionBankError(f"duplicate question ids: {q_dupes}")
        for q in self.questions:
            if q.concept not in known:
                raise QuestionBankError(f"question {q.id}: unknown concept {q.concept!r}")
        return self

    def topological_order(self) -> list[str]:
        """Concept codes ordered so every prerequisite comes before its dependants."""
        return _topological_sort({c.code: c.prerequisites for c in self.concepts})


def _topological_sort(graph: dict[str, list[str]]) -> list[str]:
    order: list[str] = []
    state: dict[str, int] = {}  # 1 = visiting, 2 = done

    def visit(node: str, path: list[str]) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            cycle = " -> ".join([*path[path.index(node) :], node])
            raise QuestionBankError(f"prerequisite cycle: {cycle}")
        state[node] = 1
        for pre in graph[node]:
            visit(pre, [*path, node])
        state[node] = 2
        order.append(node)

    for node in graph:
        visit(node, [])
    return order


def _assert_acyclic(graph: dict[str, list[str]]) -> None:
    _topological_sort(graph)


def load_question_bank(subject_dir: Path) -> QuestionBank:
    """Load concepts.yaml and every questions/*.yaml file in a subject folder."""
    concepts_doc = yaml.safe_load((subject_dir / "concepts.yaml").read_text(encoding="utf-8"))
    questions: list[dict] = []
    for path in sorted((subject_dir / "questions").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        questions.extend(doc.get("questions", []))
    return QuestionBank(
        subject=concepts_doc["subject"],
        concepts=concepts_doc["concepts"],
        questions=questions,
    )
