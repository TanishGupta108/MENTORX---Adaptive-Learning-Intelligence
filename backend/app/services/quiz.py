"""Adaptive quiz engine: sessions, serving questions, recording answers (FR-DIAG, FR-QUIZ).

Key guarantees (design decisions D-4, D-5):
- the answer key never leaves the server before the student answers;
- the server remembers which question it served and when, so an answer is accepted only
  for that question, exactly once, and response time is measured server-side;
- the model's prediction is stored BEFORE the answer, for honest live evaluation;
- each answer is one transaction with the session row locked (no double submits).
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import (
    Attempt,
    Concept,
    Enrollment,
    MasterySnapshot,
    Question,
    StudySession,
    Subject,
    User,
)
from app.ml import knowledge
from app.ml.registry import get_model
from app.schemas.sessions import (
    AnswerResult,
    ConceptSummary,
    DiagnosticSummary,
    Feedback,
    MasteryChange,
    OptionOut,
    QuestionOut,
    SessionOut,
    StartSessionRequest,
)
from app.services import engagement, learning
from app.services import mastery as mastery_service
from app.services.selection import select_index

logger = logging.getLogger(__name__)
_rng = random.SystemRandom()


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- helpers


def _subject(db: Session, code: str) -> Subject:
    s = db.scalar(select(Subject).where(Subject.code == code.upper(), Subject.is_active))
    if s is None:
        raise AppError(404, "subject_not_found", f"No active subject with code {code!r}.")
    return s


def _enrollment(db: Session, user: User, subject: Subject) -> Enrollment:
    e = db.get(Enrollment, (user.id, subject.id))
    if e is None:
        raise AppError(409, "not_enrolled", f"Enrol in {subject.code} first.")
    return e


def _own_session(
    db: Session, user: User, session_id: uuid.UUID, lock: bool = False
) -> StudySession:
    stmt = select(StudySession).where(
        StudySession.id == session_id, StudySession.user_id == user.id
    )
    if lock:
        stmt = stmt.with_for_update()
    s = db.scalar(stmt)
    if s is None:  # 404 also for other users' sessions: don't reveal that they exist
        raise AppError(404, "session_not_found", "Session not found.")
    return s


def _concepts(db: Session, subject_id: int) -> list[Concept]:
    return list(
        db.scalars(
            select(Concept).where(Concept.subject_id == subject_id).order_by(Concept.topo_order)
        )
    )


def _diagnostic_questions(db: Session, subject_id: int) -> list[Question]:
    """One diagnostic question per concept, in prerequisite (topological) order."""
    return list(
        db.scalars(
            select(Question)
            .join(Concept, Concept.id == Question.concept_id)
            .where(
                Concept.subject_id == subject_id,
                Question.is_diagnostic,
                Question.status == "active",
            )
            .order_by(Concept.topo_order, Question.id)
        )
    )


# Pre- and post-tests (FR-PILOT-02) run like the diagnostic: a fixed list of one question per
# concept, in prerequisite order, with no feedback until the end.
TEST_TYPES = ("pretest", "posttest")
FIXED_TYPES = ("diagnostic", *TEST_TYPES)


def is_participant(user: User) -> bool:
    """In the pilot: assigned a group at sign-up (pilot active) and agreed to the study."""
    return user.experiment_group is not None and user.consent_research


def test_form_for(user: User, kind: str) -> str | None:
    """Counterbalanced parallel forms: the post-test uses the form the pre-test didn't."""
    if user.pretest_form is None:
        return None
    if kind == "pretest":
        return user.pretest_form
    return "B" if user.pretest_form == "A" else "A"


def _form_questions(db: Session, subject_id: int, form: str | None) -> list[Question]:
    return list(
        db.scalars(
            select(Question)
            .join(Concept, Concept.id == Question.concept_id)
            .where(
                Concept.subject_id == subject_id,
                Question.test_form == form,
                Question.status == "active",
            )
            .order_by(Concept.topo_order, Question.id)
        )
    )


def _fixed_questions(db: Session, user: User, s: StudySession) -> list[Question]:
    if s.type == "diagnostic":
        return _diagnostic_questions(db, s.subject_id)
    return _form_questions(db, s.subject_id, test_form_for(user, s.type))


def test_done(db: Session, user: User, subject_id: int, kind: str) -> bool:
    return bool(
        db.scalar(
            select(func.count())
            .select_from(StudySession)
            .where(
                StudySession.user_id == user.id,
                StudySession.subject_id == subject_id,
                StudySession.type == kind,
                StudySession.status == "completed",
            )
        )
    )


def _finishes_diagnostic(db: Session, user: User, s: StudySession) -> bool:
    """The diagnostic, or a pre-test taken instead of it (pilot participants)."""
    if s.type == "diagnostic":
        return True
    enrollment = db.get(Enrollment, (user.id, s.subject_id))
    return s.type == "pretest" and enrollment.diagnostic_completed_at is None


def to_out(db: Session, s: StudySession) -> SessionOut:
    subject = db.get(Subject, s.subject_id)
    focus = db.get(Concept, s.focus_concept_id) if s.focus_concept_id else None
    return SessionOut(
        id=s.id,
        subject=subject.code,
        type=s.type,
        status=s.status,
        focus_concept=focus.code if focus else None,
        answered=s.answered_count,
        target=s.target_count,
        started_at=s.started_at,
        ended_at=s.ended_at,
    )


# ---------------------------------------------------------------- sessions


def start_session(db: Session, user: User, req: StartSessionRequest) -> StudySession:
    subject = _subject(db, req.subject)
    enrollment = _enrollment(db, user, subject)
    focus = None
    if req.concept:
        if req.type != "practice":
            raise AppError(
                422, "validation_error", "Only practice sessions can focus on a concept."
            )
        focus = db.scalar(
            select(Concept).where(Concept.code == req.concept, Concept.subject_id == subject.id)
        )
        if focus is None:
            raise AppError(
                404, "concept_not_found", f"No concept {req.concept!r} in {subject.code}."
            )

    active = db.scalar(
        select(StudySession)
        .where(
            StudySession.user_id == user.id,
            StudySession.subject_id == subject.id,
            StudySession.type == req.type,
            StudySession.status == "active",
        )
        .with_for_update()
    )

    if req.type == "diagnostic":
        if enrollment.diagnostic_completed_at is not None:
            raise AppError(409, "diagnostic_done", "You've already completed the diagnostic.")
        if is_participant(user) and not test_done(db, user, subject.id, "pretest"):
            raise AppError(
                409, "pretest_first", "Take the pre-test: it also sets up your starting profile."
            )
        if active:
            return active  # resume where the student left off (FR-DIAG-06)
        target = len(_diagnostic_questions(db, subject.id))
        if target == 0:
            raise AppError(409, "no_content", "This subject has no diagnostic questions yet.")
    elif req.type in TEST_TYPES:
        if not is_participant(user):
            raise AppError(
                403,
                "not_in_pilot",
                "Pre- and post-tests are only for students taking part in the study.",
            )
        if test_done(db, user, subject.id, req.type):
            raise AppError(409, f"{req.type}_done", "You've already taken this test.")
        if req.type == "posttest":
            if not test_done(db, user, subject.id, "pretest"):
                raise AppError(409, "pretest_first", "Take the pre-test first.")
            if not get_settings().posttest_open:
                raise AppError(
                    409, "posttest_closed", "The post-test opens at the end of the study."
                )
        if active:
            return active
        target = len(_form_questions(db, subject.id, test_form_for(user, req.type)))
        if target == 0:
            raise AppError(409, "no_content", "This subject has no test questions yet.")
    elif req.type == "revision":
        if active:
            return active
        if not learning.due_concepts(db, user, subject.id):
            raise AppError(409, "nothing_due", "No concepts are due for revision right now.")
        target = get_settings().revision_length  # FR-REV-03
    else:
        if active and active.focus_concept_id == (focus.id if focus else None):
            return active
        if active:  # a different practice request replaces the unfinished one
            active.status, active.ended_at = "abandoned", _now()
            db.flush()
        target = get_settings().practice_length

    session = StudySession(
        user_id=user.id,
        subject_id=subject.id,
        type=req.type,
        focus_concept_id=focus.id if focus else None,
        target_count=target,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def end_session(db: Session, user: User, session_id: uuid.UUID) -> StudySession:
    s = _own_session(db, user, session_id, lock=True)
    if s.status == "active":
        s.status, s.ended_at = "completed", _now()
        s.current_question_id = s.current_served_at = s.current_predicted_p = None
        s.current_model_version_id = None
        if _finishes_diagnostic(db, user, s):  # skipping the rest (FR-DIAG-05)
            _finish_diagnostic(db, user, s)
            learning.generate(db, user, s.subject_id, "diagnostic")
        elif s.answered_count and s.type not in TEST_TYPES:
            learning.generate(db, user, s.subject_id, "session")
        db.commit()
    return s


def list_sessions(db: Session, user: User, limit: int = 50) -> list[SessionOut]:
    rows = db.execute(
        select(StudySession, func.count(Attempt.id).filter(Attempt.is_correct))
        .outerjoin(Attempt, Attempt.session_id == StudySession.id)
        .where(StudySession.user_id == user.id)
        .group_by(StudySession.id)
        .order_by(StudySession.started_at.desc())
        .limit(limit)
    ).all()
    out = []
    for s, correct in rows:
        o = to_out(db, s)
        o.correct = int(correct)
        if s.type not in FIXED_TYPES and s.answered_count:
            o.changes = session_changes(db, s)  # FR-DASH-05
        out.append(o)
    return out


# ---------------------------------------------------------------- serving


def _target_concepts(db: Session, user: User, s: StudySession) -> list[int]:
    """Concepts a practice or revision session draws from.

    - focused practice: that concept;
    - recommended practice: the first concepts of the current learning path (FR-PATH);
    - revision: the concepts currently due, else (all revived mid-session) the ones this
      session has already revised (FR-REV-03).
    """
    cfg = get_settings()
    if s.focus_concept_id:
        return [s.focus_concept_id]
    if s.type == "revision":
        due = [c.concept.id for c in learning.due_concepts(db, user, s.subject_id)]
        if due:
            return due
        return list(
            db.scalars(
                select(Question.concept_id)
                .join(Attempt, Attempt.question_id == Question.id)
                .where(Attempt.session_id == s.id)
                .distinct()
            )
        )
    concepts = learning.path_concepts(db, user, s.subject_id, cfg.practice_path_concepts)
    if concepts:
        return concepts
    # Empty path = everything mastered: keep practising the weakest concepts.
    current = learning.states(db, user, s.subject_id, _now())
    return [c for c, _ in sorted(current.items(), key=lambda kv: kv[1].p)][
        : cfg.practice_path_concepts
    ]


def _practice_candidates(db: Session, user: User, s: StudySession) -> list[Question]:
    cfg = get_settings()
    concepts = _target_concepts(db, user, s)
    in_session = select(Attempt.question_id).where(Attempt.session_id == s.id)
    recent_correct = select(Attempt.question_id).where(
        Attempt.user_id == user.id,
        Attempt.is_correct,
        Attempt.created_at >= _now() - timedelta(days=cfg.recent_correct_exclusion_days),
    )
    base = select(Question).where(
        Question.status == "active",
        Question.test_form.is_(None),  # pre/post-test questions are never practised
        Question.id.not_in(in_session),
    )
    eligible = list(
        db.scalars(
            base.where(Question.concept_id.in_(concepts), Question.id.not_in(recent_correct))
        )
    )
    if eligible:
        return eligible
    # FR-QUIZ-04: content exhausted -> least recently seen question in the same concepts,
    # then anywhere in the subject.
    logger.warning("content_exhausted user=%s session=%s concepts=%s", user.id, s.id, concepts)
    last_seen = (
        select(Attempt.question_id, func.max(Attempt.created_at).label("seen"))
        .where(Attempt.user_id == user.id)
        .group_by(Attempt.question_id)
        .subquery()
    )
    for scope in (
        Question.concept_id.in_(concepts),
        Question.concept_id.in_(select(Concept.id).where(Concept.subject_id == s.subject_id)),
    ):
        q = db.scalar(
            base.where(scope)
            .outerjoin(last_seen, last_seen.c.question_id == Question.id)
            .order_by(last_seen.c.seen.asc().nulls_first(), Question.id)
            .limit(1)
        )
        if q:
            return [q]
    return []


def _question_out(db: Session, s: StudySession, q: Question) -> QuestionOut:
    concept = db.get(Concept, q.concept_id)
    return QuestionOut(
        session_id=s.id,
        question_id=q.id,
        concept=concept.code,
        concept_name=concept.name,
        stem=q.stem,
        options=[OptionOut(**o) for o in q.options],
        allow_dont_know=True,
        position=s.answered_count + 1,
        total=s.target_count,
    )


def next_question(db: Session, user: User, session_id: uuid.UUID) -> QuestionOut:
    s = _own_session(db, user, session_id, lock=True)
    if s.status != "active":
        raise AppError(409, "session_closed", "This session has ended.")
    if s.current_question_id is not None:  # already served and unanswered: same question again
        return _question_out(db, s, db.get(Question, s.current_question_id))

    model = get_model(db)
    now = _now()
    if s.type in FIXED_TYPES:
        answered = set(db.scalars(select(Attempt.question_id).where(Attempt.session_id == s.id)))
        remaining = [q for q in _fixed_questions(db, user, s) if q.id not in answered]
        if not remaining:
            raise AppError(409, "session_complete", "No questions left in this session.")
        chosen = remaining[0]
        p = float(
            knowledge.predict_questions(
                db, model, user.id, s.subject_id, [chosen], _codes(db, [chosen]), now
            )[0]
        )
    else:
        candidates = _practice_candidates(db, user, s)
        if not candidates:
            raise AppError(409, "no_content", "There are no questions available right now.")
        preds = knowledge.predict_questions(
            db, model, user.id, s.subject_id, candidates, _codes(db, candidates), now
        )
        cfg = get_settings()
        i = select_index(
            list(preds), user.experiment_group, cfg.target_p_correct, cfg.selection_top_k, _rng
        )
        chosen, p = candidates[i], float(preds[i])

    # Store what was served, when, and what the model predicted, BEFORE the answer (D-4).
    s.current_question_id = chosen.id
    s.current_served_at = now
    s.current_predicted_p = p
    s.current_model_version_id = model.version_id
    db.commit()
    return _question_out(db, s, chosen)


def _codes(db: Session, questions: list[Question]) -> dict[int, str]:
    ids = {q.concept_id for q in questions}
    return dict(db.execute(select(Concept.id, Concept.code).where(Concept.id.in_(ids))).all())


# ---------------------------------------------------------------- answering


def answer(
    db: Session, user: User, session_id: uuid.UUID, question_id: int, selected_key: str | None
) -> AnswerResult:
    s = _own_session(db, user, session_id, lock=True)  # row lock: no double submits
    if s.status != "active":
        raise AppError(409, "session_closed", "This session has ended.")
    if s.current_question_id is None or s.current_question_id != question_id:
        raise AppError(
            409, "question_mismatch", "That isn't the question currently served in this session."
        )

    cfg = get_settings()
    now = _now()
    q = db.get(Question, question_id)
    is_correct = selected_key is not None and selected_key == q.correct_key
    response_ms = max(0, int((now - s.current_served_at).total_seconds() * 1000))
    previous = db.scalar(
        select(func.count())
        .select_from(Attempt)
        .where(Attempt.user_id == user.id, Attempt.question_id == question_id)
    )
    attempt = Attempt(
        user_id=user.id,
        session_id=s.id,
        question_id=question_id,
        selected_key=selected_key,
        is_correct=is_correct,
        response_ms=response_ms,
        attempt_no=previous + 1,
        # FR-ENG-02: answers under the minimum time are treated as possible rapid guesses.
        # (Any "run" of fast answers consists of such answers, so this single check covers it.)
        is_valid=response_ms >= cfg.valid_answer_min_ms,
        predicted_p_correct=s.current_predicted_p,
        model_version_id=s.current_model_version_id,
        created_at=now,
    )
    db.add(attempt)
    s.answered_count += 1
    s.current_question_id = s.current_served_at = s.current_predicted_p = None
    s.current_model_version_id = None
    db.flush()

    model = get_model(db)
    concept = db.get(Concept, q.concept_id)
    change = mastery_service.recompute(db, model, user.id, s.subject_id, [concept], now, attempt.id)
    before, after = change[concept.id]

    complete = s.answered_count >= s.target_count
    summary = changes = None
    if complete:
        s.status, s.ended_at = "completed", now
        if _finishes_diagnostic(db, user, s):
            summary = _finish_diagnostic(db, user, s)
            learning.generate(db, user, s.subject_id, "diagnostic", now)  # FR-PATH-04
        elif s.type in TEST_TYPES:
            pass  # a measurement: no path regeneration, no per-session summary
        else:
            changes = session_changes(db, s)
            learning.generate(db, user, s.subject_id, "session", now)
    goal = engagement.record_progress(db, user, now)
    db.commit()

    is_diag = s.type in FIXED_TYPES
    return AnswerResult(
        feedback=None
        if is_diag
        else Feedback(correct=is_correct, correct_key=q.correct_key, explanation=q.explanation),
        mastery=None
        if is_diag
        else MasteryChange(concept=concept.code, before=before, after=after),
        answered=s.answered_count,
        target=s.target_count,
        session_complete=complete,
        summary=summary,
        changes=changes,
        goal=goal,
    )


def _finish_diagnostic(db: Session, user: User, s: StudySession) -> DiagnosticSummary:
    """FR-DIAG-04: mastery for EVERY concept, and a summary of strengths and gaps."""
    enrollment = db.get(Enrollment, (user.id, s.subject_id))
    enrollment.diagnostic_completed_at = _now()
    concepts = _concepts(db, s.subject_id)
    change = mastery_service.recompute(db, get_model(db), user.id, s.subject_id, concepts, _now())
    ranked = sorted(
        (
            ConceptSummary(concept=c.code, name=c.name, mastery=change[c.id][1])
            for c in concepts
            if c.id in change
        ),
        key=lambda x: x.mastery,
    )
    return DiagnosticSummary(strongest=list(reversed(ranked[-3:])), weakest=ranked[:3])


def session_changes(db: Session, s: StudySession) -> list[MasteryChange]:
    """FR-REV-04: each practised concept's mastery just before and just after this session.

    From the mastery snapshots taken after every answer: "after" is the snapshot of the
    session's last answer on that concept, "before" the latest snapshot preceding the
    session's first one (null if the concept had none).
    """
    db.flush()  # autoflush is off: include this request's snapshots
    snaps = db.execute(
        select(MasterySnapshot.concept_id, MasterySnapshot.id, MasterySnapshot.p_mastery)
        .join(Attempt, Attempt.id == MasterySnapshot.attempt_id)
        .where(Attempt.session_id == s.id)
        .order_by(MasterySnapshot.id)
    ).all()
    first: dict[int, int] = {}
    after: dict[int, float] = {}
    for cid, sid, p in snaps:
        first.setdefault(cid, sid)
        after[cid] = p
    codes = dict(db.execute(select(Concept.id, Concept.code).where(Concept.id.in_(first))).all())
    out = []
    for cid, first_id in first.items():
        before = db.scalar(
            select(MasterySnapshot.p_mastery)
            .where(
                MasterySnapshot.user_id == s.user_id,
                MasterySnapshot.concept_id == cid,
                MasterySnapshot.id < first_id,
            )
            .order_by(MasterySnapshot.id.desc())
            .limit(1)
        )
        out.append(MasteryChange(concept=codes[cid], before=before, after=after[cid]))
    return sorted(out, key=lambda c: c.concept)


def session_detail(db: Session, user: User, session_id: uuid.UUID) -> SessionOut:
    s = _own_session(db, user, session_id)
    out = to_out(db, s)
    if s.type not in FIXED_TYPES:
        out.changes = session_changes(db, s)
    return out
