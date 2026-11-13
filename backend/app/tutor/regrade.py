"""Re-check stored answers with the current answer checker (v3 numeric policy).

Only wrong -> right changes are made, and only for typed answers (numeric,
numeric_expression, exact_match): an answer that the old checker wrongly marked incorrect
(e.g. 3.67 for 11/3) becomes correct. Nothing is ever changed from right to wrong.
For each change: `is_correct = True`; `model_label = True` only if no hint was used and the
answer wasn't revealed; `response["regraded_at"]` records when; the session's correct count
goes up by one; AI explanations cached for that wrong answer are hidden (they would tell the
student a right answer was wrong). Affected students' skill states and recommendations are
then rebuilt for that subject. Running it again changes nothing (idempotent).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.tutor import ai, answers, recommend, state
from app.tutor.models import AiExplanation, Assessment, Interaction, Item, PracticeSession

logger = logging.getLogger(__name__)
TYPES = ("numeric", "numeric_expression", "exact_match")


@dataclass
class RegradeReport:
    checked: int = 0
    changed: int = 0
    unreadable: int = 0
    explanations_hidden: int = 0
    users: int = 0
    items: set[int] = field(default_factory=set)
    changes: list[tuple[int, int]] = field(default_factory=list)  # (item id, interaction id)

    def lines(self) -> list[str]:
        return [
            f"answers checked: {self.checked}",
            f"wrong -> correct: {self.changed} (on {len(self.items)} questions)",
            f"unreadable with today's checker (left as they are): {self.unreadable}",
            f"AI explanations hidden: {self.explanations_hidden}",
            f"students refreshed: {self.users}",
        ]


def regrade(db: Session, dry_run: bool = False) -> RegradeReport:
    rep = RegradeReport()
    rows = db.execute(
        select(Interaction, Item)
        .join(Item, Item.id == Interaction.item_id)
        .where(
            Item.answer_type.in_(TYPES),
            ~Interaction.is_correct,
            ~Interaction.saw_answer,
        )
        .order_by(Interaction.id)
    ).all()
    now = datetime.now(UTC).isoformat()
    affected: set[tuple] = set()
    sigs: dict[int, set[str]] = {}
    for inter, item in rows:
        rep.checked += 1
        response = dict(inter.response or {})
        if "value" not in response:
            continue
        try:
            ok = answers.check(item.answer_type, item.answer_key, response, item.body_html)
        except ValueError:
            rep.unreadable += 1
            continue
        if not ok:
            continue
        rep.changed += 1
        rep.items.add(item.id)
        rep.changes.append((item.id, inter.id))
        logger.info("regrade item %s interaction %s: wrong -> correct", item.id, inter.id)
        sigs.setdefault(item.id, set()).add(ai.wrong_signature(inter.response or {}))
        affected.add((inter.user_id, item.subject_id))
        if dry_run:
            continue
        inter.is_correct = True
        inter.model_label = not inter.hint_used and not inter.saw_answer
        inter.response = {**response, "regraded_at": now}
        if inter.assessment_id is not None:
            a = db.get(Assessment, inter.assessment_id)
            if a is not None:
                a.correct_count = min(a.correct_count + 1, a.answered_count)
        if inter.practice_id is not None:
            p = db.get(PracticeSession, inter.practice_id)
            if p is not None:
                p.correct_count = min(p.correct_count + 1, p.answered_count)
    if dry_run:
        for item_id, s in sigs.items():
            rep.explanations_hidden += len(
                db.scalars(
                    select(AiExplanation.id).where(
                        AiExplanation.item_id == item_id,
                        AiExplanation.kind == "explanation",
                        AiExplanation.answer_sig.in_(list(s)),
                        AiExplanation.status == "ok",
                    )
                ).all()
            )
    else:
        for item_id, s in sigs.items():
            rep.explanations_hidden += ai.hide_explanations(db, db.get(Item, item_id), s)
        db.flush()
        for user_id, subject_id in sorted(affected, key=str):
            state.refresh(db, user_id, subject_id)
            recommend.generate(db, user_id, "regrade", subject_id=subject_id)
        db.commit()
    rep.users = len({u for u, _ in affected})
    return rep
