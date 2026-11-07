"""Load and validate a subject's question bank from YAML.

Used by tests (so a bad question can never be merged) and, from M5, by the
seed script that loads questions into the database.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9]+-\d{3,}$")
    concept: str
    difficulty: Literal[1, 2, 3]
    diagnostic: bool = False
    # Pre/post-test parallel forms. These questions are never used in practice.
    test_form: Literal["A", "B"] | None = None
    # Only "reviewed" questions are loaded in production (see docs/question-bank-guide.md).
    review_status: Literal["draft", "reviewed"] = "draft"
    stem: str = Field(min_length=10)
    options: dict[OptionKey, str]
    answer: OptionKey
    explanation: str = Field(min_length=20)

    @model_validator(mode="after")
    def diagnostic_is_not_a_test_question(self) -> QuestionSpec:
        if self.diagnostic and self.test_form:
            raise ValueError(f"{self.id}: a question can't be both diagnostic and a test form")
        return self

    @property
    def is_practice(self) -> bool:
        return not self.diagnostic and self.test_form is None

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

        stems = Counter(" ".join(q.stem.lower().split()) for q in self.questions)
        repeated = [s[:60] for s, n in stems.items() if n > 1]
        if repeated:
            raise QuestionBankError(f"duplicate question stems: {repeated}")
        return self

    def topological_order(self) -> list[str]:
        """Concept codes ordered so every prerequisite comes before its dependants."""
        return _topological_sort({c.code: c.prerequisites for c in self.concepts})

    def coverage_problems(self, standard: CoverageStandard | None = None) -> list[str]:
        """Content-completeness problems (empty list = the bank meets the standard).

        Kept separate from hard validation so a half-written bank still loads in
        development, while tests can require the full standard.
        """
        std = standard or CoverageStandard()
        problems: list[str] = []
        for c in self.concepts:
            qs = [q for q in self.questions if q.concept == c.code]
            n_diag = sum(q.diagnostic for q in qs)
            if n_diag != 1:
                problems.append(f"{c.code}: needs exactly 1 diagnostic question, has {n_diag}")
            for form in ("A", "B"):
                n_form = sum(q.test_form == form for q in qs)
                if n_form != 1:
                    problems.append(f"{c.code}: needs exactly 1 form-{form} question, has {n_form}")
            forms = {q.test_form: q.difficulty for q in qs if q.test_form}
            if len(forms) == 2 and forms["A"] != forms["B"]:
                problems.append(f"{c.code}: form A and form B questions differ in difficulty")
            practice = [q for q in qs if q.is_practice]
            if len(practice) < std.min_practice_per_concept:
                problems.append(
                    f"{c.code}: {len(practice)} practice questions "
                    f"(minimum {std.min_practice_per_concept})"
                )
            missing = {1, 2, 3} - {q.difficulty for q in practice}
            if missing:
                problems.append(f"{c.code}: no practice questions at difficulty {sorted(missing)}")

        # The answer letter must be unpredictable overall AND within each fixed test
        # (diagnostic, form A, form B), or "always guess B" inflates scores.
        groups = {
            "all questions": self.questions,
            "diagnostic": [q for q in self.questions if q.diagnostic],
            "form A": [q for q in self.questions if q.test_form == "A"],
            "form B": [q for q in self.questions if q.test_form == "B"],
        }
        for name, qs in groups.items():
            if not qs:
                continue
            lo, hi = (
                (std.min_answer_share, std.max_answer_share)
                if name == "all questions"
                else (std.min_test_answer_share, std.max_test_answer_share)
            )
            counts = Counter(q.answer for q in qs)
            for key in "ABCD":
                share = counts[key] / len(qs)
                if not lo <= share <= hi:
                    problems.append(
                        f"{name}: answer {key} is correct in {share:.0%} "
                        f"(allowed {lo:.0%}-{hi:.0%})"
                    )
        return problems


class CoverageStandard(BaseModel):
    """The M2 content standard (see docs/question-bank-guide.md)."""

    min_practice_per_concept: int = 12
    # Keeps the correct letter unpredictable: no key should be right far more often than 25%.
    min_answer_share: float = 0.18
    max_answer_share: float = 0.32
    # Fixed tests are short (one question per concept), so allow a little more spread.
    min_test_answer_share: float = 0.15
    max_test_answer_share: float = 0.35


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
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise QuestionBankError(f"{path.name}: invalid YAML: {exc}") from exc
        questions.extend(doc.get("questions", []))
    return QuestionBank(
        subject=concepts_doc["subject"],
        concepts=concepts_doc["concepts"],
        questions=questions,
    )
