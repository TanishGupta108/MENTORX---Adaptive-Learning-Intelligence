"""The one-off regrade: wrong -> right under the v3 numeric policy, audited and idempotent."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.models import User
from app.tutor.html import sanitize
from app.tutor.models import AiExplanation, Interaction, Item, Skill, SkillState
from app.tutor.regrade import regrade


def _setup(db) -> tuple[User, Item]:
    user = db.scalar(select(User).where(User.email == "student@example.com"))
    skill = db.get(Skill, 129)
    item = Item(
        id=990001, subject_id=skill.subject_id, skill_id=129, answer_type="numeric",
        body_html=sanitize('<p>How many pounds for $11.00?</p><ast-r></ast-r> pounds'),
        options=[], answer_key=["11/3"], difficulty="medium", n_skills=1, is_active=True,
    )  # fmt: skip
    db.add(item)
    db.flush()
    return user, item


def _answer(db, user, item, value, *, correct=False, hint=False, at=None):
    i = Interaction(
        user_id=user.id, item_id=item.id, skill_id=item.skill_id, n_skills=1, context="practice",
        response={"value": value}, is_correct=correct, hint_used=hint, model_label=correct,
        created_at=at or datetime.now(UTC),
    )  # fmt: skip
    db.add(i)
    db.flush()
    return i


def test_regrade_wrong_to_right_only(client, math_keys, learner, db):
    from app.tutor.ai import wrong_signature

    user, item = _setup(db)
    t = datetime.now(UTC) - timedelta(minutes=5)
    good = _answer(db, user, item, "3.67", at=t)
    hinted = _answer(db, user, item, "3 2/3", hint=True, at=t + timedelta(seconds=1))
    bad = _answer(db, user, item, "3.66", at=t + timedelta(seconds=2))
    junk = _answer(db, user, item, "three", at=t + timedelta(seconds=3))
    db.add(
        AiExplanation(
            item_id=item.id, kind="explanation", answer_sig=wrong_signature({"value": "3.67"}),
            content="Rounding loses precision.", model="m",
        )
    )  # fmt: skip
    db.commit()

    dry = regrade(db, dry_run=True)
    assert dry.changed == 2  # 3.67 (rounded) and 3 2/3 (exact); 3.66 stays wrong
    assert dry.explanations_hidden == 1 and dry.unreadable == 1
    db.expire_all()
    assert not db.get(Interaction, good.id).is_correct  # dry run changed nothing

    rep = regrade(db)
    assert rep.changed == dry.changed and rep.users == 1
    db.expire_all()
    g, h, b = (db.get(Interaction, x.id) for x in (good, hinted, bad))
    assert g.is_correct and g.model_label and "regraded_at" in g.response
    assert h.is_correct and not h.model_label  # a hint was used: not the model's "correct"
    assert not b.is_correct and not db.get(Interaction, junk.id).is_correct
    assert db.scalar(select(AiExplanation.status)) == "hidden"
    st = db.get(SkillState, (user.id, 129))
    assert st.correct >= 2  # the skill state was rebuilt

    again = regrade(db)
    assert again.changed == 0 and again.explanations_hidden == 0  # idempotent
