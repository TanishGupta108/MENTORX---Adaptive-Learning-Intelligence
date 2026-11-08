"""The pilot study (M11): status, SUS survey, admin metrics and pseudonymised exports.

FR-PILOT-01..05, FR-DASH-09. See docs/modules/pilot.md.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import math
import statistics
import uuid
from datetime import UTC, datetime, timedelta

from scipy import stats
from sklearn.metrics import roc_auc_score
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import (
    Attempt,
    Concept,
    Feedback,
    ModelVersion,
    Question,
    StudySession,
    Subject,
    SusResponse,
    User,
)
from app.schemas.pilot import (
    CalibrationBin,
    Engagement,
    FeedbackSummary,
    GroupOutcome,
    ModelQuality,
    PilotMetrics,
    PilotStatus,
    SusOut,
    SusRequest,
    TestState,
)
from app.services import quiz

GROUPS = ("adaptive", "control")
CALIBRATION_BINS = 10


# ---------------------------------------------------------------- student side


def _subject(db: Session, code: str) -> Subject:
    return quiz._subject(db, code)


def _test_state(db: Session, user: User, subject: Subject, kind: str) -> TestState:
    form = quiz.test_form_for(user, kind)
    n = len(quiz._form_questions(db, subject.id, form)) if form else 0
    if quiz.test_done(db, user, subject.id, kind):
        return TestState(status="done", questions=n)
    available = quiz.is_participant(user) and n > 0
    if kind == "posttest":
        available = (
            available
            and quiz.test_done(db, user, subject.id, "pretest")
            and get_settings().posttest_open
        )
    if not available:
        return TestState(status="unavailable", questions=n)
    active = db.scalar(
        select(StudySession.id).where(
            StudySession.user_id == user.id,
            StudySession.subject_id == subject.id,
            StudySession.type == kind,
            StudySession.status == "active",
        )
    )
    return TestState(status="in_progress" if active else "todo", session_id=active, questions=n)


def status(db: Session, user: User, code: str) -> PilotStatus:
    subject = _subject(db, code)
    return PilotStatus(
        pilot_active=get_settings().pilot_active,
        in_study=user.experiment_group is not None,
        consented=user.consent_research,
        pretest=_test_state(db, user, subject, "pretest"),
        posttest=_test_state(db, user, subject, "posttest"),
        sus_done=db.get(SusResponse, user.id) is not None,
    )


def sus_score(answers: list[int]) -> float:
    """Standard SUS scoring: odd items contribute (a - 1), even items (5 - a); sum x 2.5."""
    if len(answers) != 10 or any(a not in (1, 2, 3, 4, 5) for a in answers):
        raise AppError(422, "validation_error", "Answer all 10 statements with 1 to 5.")
    return 2.5 * sum((a - 1) if i % 2 == 0 else (5 - a) for i, a in enumerate(answers))


def submit_sus(db: Session, user: User, code: str, req: SusRequest) -> SusOut:
    subject = _subject(db, code)
    if not quiz.test_done(db, user, subject.id, "posttest"):
        raise AppError(409, "posttest_first", "The questionnaire comes after the post-test.")
    if db.get(SusResponse, user.id) is not None:
        raise AppError(409, "sus_done", "You've already answered the questionnaire. Thank you!")
    score = sus_score(req.answers)
    db.add(
        SusResponse(user_id=user.id, answers=req.answers, score=score, comment=req.comment.strip())
    )
    db.commit()
    return SusOut(score=score)


# ---------------------------------------------------------------- admin: helpers


def is_admin(user: User) -> bool:
    return user.role == "admin" or user.email.lower() in get_settings().admin_email_set


def _students(db: Session) -> list[User]:
    admins = get_settings().admin_email_set
    return [
        u
        for u in db.scalars(select(User).where(User.role == "student"))
        if u.email.lower() not in admins
    ]


def pseudonym(user_id: uuid.UUID) -> str:
    """Stable, non-reversible student ID for exports (FR-PILOT-05)."""
    key = (get_settings().jwt_secret + "|pseudonym").encode()
    return hmac.new(key, str(user_id).encode(), hashlib.sha256).hexdigest()[:12]


def _test_scores(db: Session) -> dict[uuid.UUID, dict[str, float]]:
    """Fraction correct on each completed pre/post-test (unanswered questions count as wrong)."""
    rows = db.execute(
        select(
            StudySession.user_id,
            StudySession.type,
            StudySession.target_count,
            func.count(Attempt.id).filter(Attempt.is_correct),
        )
        .outerjoin(Attempt, Attempt.session_id == StudySession.id)
        .where(StudySession.type.in_(quiz.TEST_TYPES), StudySession.status == "completed")
        .group_by(StudySession.id)
    ).all()
    out: dict[uuid.UUID, dict[str, float]] = {}
    for uid, kind, target, correct in rows:
        out.setdefault(uid, {})[kind] = correct / target if target else 0.0
    return out


def _mean_ci(xs: list[float]) -> tuple[float, float] | None:
    if len(xs) < 2:
        return None
    m, sd = statistics.fmean(xs), statistics.stdev(xs)
    half = stats.t.ppf(0.975, len(xs) - 1) * sd / math.sqrt(len(xs))
    return (m - half, m + half)


def _welch(a: list[float], c: list[float]):
    """Adaptive minus control: difference, Welch 95% CI and Cohen's d (pooled SD)."""
    if len(a) < 2 or len(c) < 2:
        return None, None, None
    ma, mc = statistics.fmean(a), statistics.fmean(c)
    va, vc = statistics.variance(a), statistics.variance(c)
    se = math.sqrt(va / len(a) + vc / len(c))
    diff = ma - mc
    pooled = math.sqrt(((len(a) - 1) * va + (len(c) - 1) * vc) / (len(a) + len(c) - 2))
    d = diff / pooled if pooled > 0 else None
    if se == 0:
        return diff, None, d
    df = (va / len(a) + vc / len(c)) ** 2 / (
        (va / len(a)) ** 2 / (len(a) - 1) + (vc / len(c)) ** 2 / (len(c) - 1)
    )
    half = stats.t.ppf(0.975, df) * se
    return diff, (diff - half, diff + half), d


# ---------------------------------------------------------------- admin: metrics


def metrics(db: Session) -> PilotMetrics:
    cfg = get_settings()
    students = _students(db)
    ids = [u.id for u in students]
    scores = _test_scores(db)
    sus = {r.user_id: r.score for r in db.scalars(select(SusResponse))}

    groups, gains = [], {}
    for g in GROUPS:
        members = [u for u in students if u.experiment_group == g and u.consent_research]
        pre = [scores[u.id]["pretest"] for u in members if "pretest" in scores.get(u.id, {})]
        post = [scores[u.id]["posttest"] for u in members if "posttest" in scores.get(u.id, {})]
        gain = [
            scores[u.id]["posttest"] - scores[u.id]["pretest"]
            for u in members
            if {"pretest", "posttest"} <= scores.get(u.id, {}).keys()
        ]
        gains[g] = gain
        sus_scores = [sus[u.id] for u in members if u.id in sus]
        groups.append(
            GroupOutcome(
                group=g,
                participants=len(members),
                pretest_done=len(pre),
                posttest_done=len(post),
                mean_pre=statistics.fmean(pre) if pre else None,
                mean_post=statistics.fmean(post) if post else None,
                mean_gain=statistics.fmean(gain) if gain else None,
                gain_ci95=_mean_ci(gain),
                sus_n=len(sus_scores),
                sus_mean=statistics.fmean(sus_scores) if sus_scores else None,
            )
        )
    diff, diff_ci, d = _welch(gains["adaptive"], gains["control"])

    return PilotMetrics(
        pilot_active=cfg.pilot_active,
        posttest_open=cfg.posttest_open,
        groups=groups,
        gain_difference=diff,
        gain_difference_ci95=diff_ci,
        cohens_d=d,
        engagement=_engagement(db, students),
        model=_model_quality(db, ids),
        feedback=_feedback(db),
    )


def _engagement(db: Session, students: list[User]) -> Engagement:
    now = datetime.now(UTC)
    ids = [u.id for u in students]
    times: dict[uuid.UUID, list[datetime]] = {}
    for uid, at in db.execute(
        select(Attempt.user_id, Attempt.created_at).where(Attempt.user_id.in_(ids))
    ):
        times.setdefault(uid, []).append(at)

    def retention(day: int) -> float | None:
        eligible = [u for u in students if u.created_at + timedelta(days=day + 1) <= now]
        if not eligible:
            return None
        active = sum(
            any(
                u.created_at + timedelta(days=day) <= t < u.created_at + timedelta(days=day + 1)
                for t in times.get(u.id, [])
            )
            for u in eligible
        )
        return active / len(eligible)

    week_ago = now - timedelta(days=7)
    sessions = db.execute(
        select(StudySession.status, func.count())
        .where(StudySession.user_id.in_(ids))
        .group_by(StudySession.status)
    ).all()
    by_status = dict(sessions)
    started = sum(by_status.values())
    return Engagement(
        students=len(students),
        wau=sum(any(t >= week_ago for t in ts) for ts in times.values()),
        d1_retention=retention(1),
        d7_retention=retention(7),
        sessions_started=started,
        completion_rate=by_status.get("completed", 0) / started if started else None,
    )


def _model_quality(db: Session, ids: list[uuid.UUID]) -> ModelQuality:
    """Live AUC and calibration from the prediction stored with every served question."""
    rows = db.execute(
        select(Attempt.predicted_p_correct, Attempt.is_correct).where(
            Attempt.user_id.in_(ids), Attempt.predicted_p_correct.is_not(None)
        )
    ).all()
    if not rows:
        return ModelQuality(n=0, auc=None, brier=None, ece=None, bins=[])
    p = [float(r[0]) for r in rows]
    y = [int(r[1]) for r in rows]
    auc = float(roc_auc_score(y, p)) if 0 < sum(y) < len(y) else None
    brier = statistics.fmean((pi - yi) ** 2 for pi, yi in zip(p, y, strict=True))
    bins, ece = [], 0.0
    for b in range(CALIBRATION_BINS):
        lo, hi = b / CALIBRATION_BINS, (b + 1) / CALIBRATION_BINS
        idx = [
            i for i, pi in enumerate(p) if lo <= pi < hi or (b == CALIBRATION_BINS - 1 and pi == 1)
        ]
        if not idx:
            continue
        mp = statistics.fmean(p[i] for i in idx)
        obs = statistics.fmean(y[i] for i in idx)
        ece += len(idx) / len(p) * abs(mp - obs)
        bins.append(CalibrationBin(lo=lo, hi=hi, n=len(idx), mean_predicted=mp, observed=obs))
    return ModelQuality(n=len(p), auc=auc, brier=brier, ece=ece, bins=bins)


def _feedback(db: Session) -> FeedbackSummary:
    n, mean = db.execute(select(func.count(), func.avg(Feedback.rating))).one()
    recent = db.scalars(select(Feedback).order_by(Feedback.created_at.desc()).limit(20)).all()
    return FeedbackSummary(
        n=n,
        mean_rating=float(mean) if mean is not None else None,
        recent=[
            {
                "rating": f.rating,
                "category": f.category,
                "message": f.message,
                "page": f.page,
                "at": f.created_at.isoformat(),
            }
            for f in recent
        ],
    )


# ---------------------------------------------------------------- admin: exports


def _csv(header: list[str], rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def export_attempts(db: Session) -> str:
    """FR-PILOT-05: every answer of consenting students, pseudonymised, for model training."""
    ids = [u.id for u in _students(db) if u.consent_research]
    rows = db.execute(
        select(
            Attempt,
            User.experiment_group,
            StudySession.type,
            Question.external_id,
            Question.version,
            Question.author_difficulty,
            Concept.code,
            ModelVersion.name,
        )
        .join(User, User.id == Attempt.user_id)
        .join(StudySession, StudySession.id == Attempt.session_id)
        .join(Question, Question.id == Attempt.question_id)
        .join(Concept, Concept.id == Question.concept_id)
        .outerjoin(ModelVersion, ModelVersion.id == Attempt.model_version_id)
        .where(Attempt.user_id.in_(ids))
        .order_by(Attempt.user_id, Attempt.created_at, Attempt.id)
    ).all()
    return _csv(
        [
            "student",
            "group",
            "attempt_id",
            "timestamp",
            "session_type",
            "question",
            "question_version",
            "concept",
            "difficulty",
            "correct",
            "dont_know",
            "response_ms",
            "attempt_no",
            "valid",
            "predicted_p_correct",
            "model_version",
        ],
        (
            [
                pseudonym(a.user_id),
                group or "",
                a.id,
                a.created_at.isoformat(),
                kind,
                qid,
                version,
                concept,
                difficulty,
                int(a.is_correct),
                int(a.selected_key is None),
                a.response_ms,
                a.attempt_no,
                int(a.is_valid),
                "" if a.predicted_p_correct is None else round(a.predicted_p_correct, 6),
                model or "",
            ]
            for a, group, kind, qid, version, difficulty, concept, model in rows
        ),
    )


def export_outcomes(db: Session) -> str:
    """One row per consenting participant: group, test scores, gain, SUS, activity."""
    scores = _test_scores(db)
    sus = {r.user_id: r.score for r in db.scalars(select(SusResponse))}
    participants = [u for u in _students(db) if u.consent_research and u.experiment_group]
    activity = dict(
        db.execute(
            select(Attempt.user_id, func.count())
            .where(Attempt.user_id.in_([u.id for u in participants]))
            .group_by(Attempt.user_id)
        ).all()
    )

    def fmt(x):
        return "" if x is None else round(x, 6)

    rows = []
    for u in participants:
        s = scores.get(u.id, {})
        pre, post = s.get("pretest"), s.get("posttest")
        rows.append(
            [
                pseudonym(u.id),
                u.experiment_group,
                u.pretest_form,
                fmt(pre),
                fmt(post),
                fmt(post - pre if pre is not None and post is not None else None),
                fmt(sus.get(u.id)),
                activity.get(u.id, 0),
            ]
        )
    return _csv(["student", "group", "pretest_form", "pre", "post", "gain", "sus", "answers"], rows)
