from __future__ import annotations

from pydantic import BaseModel


class SubjectOut(BaseModel):
    code: str
    name: str
    description: str
    concept_count: int
    enrolled: bool


class EnrollmentOut(BaseModel):
    subject: str
    enrolled: bool
    diagnostic_completed: bool


class ConceptOut(BaseModel):
    code: str
    name: str
    description: str
    topo_order: int
    prerequisites: list[str]
    # The student's current mastery estimate; null until they have answered on this concept.
    mastery: float | None
    n_attempts: int
