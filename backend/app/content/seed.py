"""Load a validated question bank into the database (FR-CONT-03..07).

Idempotent: running it twice changes nothing. Rules:
- subject and concepts are upserted by code; prerequisites are synced exactly;
- a new question id -> inserted as version 1;
- an existing id whose content changed -> the old version is retired and a new
  version inserted, so past attempts stay linked to what the student actually saw;
- an id no longer in the YAML (or excluded as a draft) -> retired, never deleted.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.content.question_bank import QuestionBank, QuestionSpec
from app.db.models import Concept, ConceptPrerequisite, Question, Subject

logger = logging.getLogger(__name__)


@dataclass
class SeedReport:
    concepts_created: int = 0
    concepts_updated: int = 0
    questions_created: int = 0
    questions_versioned: int = 0
    questions_retired: int = 0
    questions_unchanged: int = 0
    drafts_skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"concepts: +{self.concepts_created} created, {self.concepts_updated} updated | "
            f"questions: +{self.questions_created} new, {self.questions_versioned} new versions, "
            f"{self.questions_retired} retired, {self.questions_unchanged} unchanged, "
            f"{self.drafts_skipped} drafts skipped"
        )


def content_hash(q: QuestionSpec) -> str:
    payload = {
        "concept": q.concept,
        "difficulty": q.difficulty,
        "diagnostic": q.diagnostic,
        "test_form": q.test_form,
        "stem": q.stem,
        "options": q.options,
        "answer": q.answer,
        "explanation": q.explanation,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _question_row(q: QuestionSpec, concept_id: int, version: int) -> Question:
    return Question(
        external_id=q.id,
        version=version,
        concept_id=concept_id,
        stem=q.stem,
        options=[{"key": k, "text": t} for k, t in sorted(q.options.items())],
        correct_key=q.answer,
        explanation=q.explanation,
        author_difficulty=q.difficulty,
        is_diagnostic=q.diagnostic,
        test_form=q.test_form,
        status="active",
        content_hash=content_hash(q),
    )


def seed(db: Session, bank: QuestionBank, include_drafts: bool) -> SeedReport:
    report = SeedReport()

    subject = db.scalar(select(Subject).where(Subject.code == bank.subject.code))
    if subject is None:
        subject = Subject(
            code=bank.subject.code, name=bank.subject.name, description=bank.subject.description
        )
        db.add(subject)
    else:
        subject.name, subject.description = bank.subject.name, bank.subject.description
    db.flush()

    # --- concepts ---
    order = {code: i for i, code in enumerate(bank.topological_order())}
    existing = {
        c.code: c for c in db.scalars(select(Concept).where(Concept.subject_id == subject.id))
    }
    for spec in bank.concepts:
        c = existing.get(spec.code)
        if c is None:
            c = Concept(subject_id=subject.id, code=spec.code)
            db.add(c)
            existing[spec.code] = c
            report.concepts_created += 1
        elif (c.name, c.description, c.topo_order) != (
            spec.name,
            spec.description,
            order[spec.code],
        ):
            report.concepts_updated += 1
        c.name, c.description, c.topo_order = spec.name, spec.description, order[spec.code]
    db.flush()
    orphans = set(existing) - {s.code for s in bank.concepts}
    if orphans:
        report.warnings.append(
            f"concepts in the database but not in the YAML were left untouched: {sorted(orphans)}"
        )

    ids = [existing[s.code].id for s in bank.concepts]
    db.execute(delete(ConceptPrerequisite).where(ConceptPrerequisite.concept_id.in_(ids)))
    for spec in bank.concepts:
        for pre in spec.prerequisites:
            db.add(
                ConceptPrerequisite(
                    concept_id=existing[spec.code].id, prerequisite_id=existing[pre].id
                )
            )

    # --- questions ---
    wanted = [q for q in bank.questions if include_drafts or q.review_status == "reviewed"]
    report.drafts_skipped = len(bank.questions) - len(wanted)
    wanted_ids = {q.id for q in wanted}
    concept_ids = set(ids)
    active = {
        q.external_id: q
        for q in db.scalars(
            select(Question).where(
                Question.status == "active", Question.concept_id.in_(concept_ids)
            )
        )
    }
    latest_version = dict(
        db.execute(
            select(Question.external_id, func.max(Question.version))
            .where(Question.concept_id.in_(concept_ids))
            .group_by(Question.external_id)
        ).all()
    )

    for ext_id, row in active.items():
        if ext_id not in wanted_ids:
            row.status = "retired"
            report.questions_retired += 1
    db.flush()  # retire before inserting new versions (one active version per id)

    for q in wanted:
        concept_id = existing[q.concept].id
        row = active.get(q.id)
        if row is not None and row.content_hash == content_hash(q):
            report.questions_unchanged += 1
            continue
        if row is not None:
            row.status = "retired"
            db.flush()
            report.questions_versioned += 1
        else:
            report.questions_created += 1
        db.add(_question_row(q, concept_id, latest_version.get(q.id, 0) + 1))
    db.commit()
    logger.info("seed %s: %s", bank.subject.code, report.summary())
    return report
