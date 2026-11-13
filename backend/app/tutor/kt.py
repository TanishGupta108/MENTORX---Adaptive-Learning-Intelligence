"""Model serving for the tutor: one exported knowledge-tracing model per subject, loaded once,
that turns a student's interaction log IN THAT SUBJECT into predictions.

Kept separate from answer checking and recommendation rules (they only consume numbers).
If a subject's artifacts are missing the service reports `available = False` for it and every
caller shows observed performance only. Nothing is ever labelled as a model prediction unless
it came from the real model. Each model only ever sees its own subject's interactions
(question and skill ids of different subjects never mix).

Subjects register their model in config `KT_SUBJECTS` ("CODE=dir,..."); MATH defaults to
`KT_ARTIFACTS_DIR`.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ml.dkt import Attempt, KTInference
from app.tutor import engine
from app.tutor.models import Interaction, Item, Skill

logger = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CODE = "MATH"
_lock = threading.Lock()


@dataclass
class ModelInfo:
    available: bool
    name: str | None = None
    display_name: str | None = None
    test_auc: float | None = None
    test_accuracy: float | None = None
    parameters: int | None = None
    reason: str | None = None


@lru_cache(maxsize=16)
def _load(code: str) -> KTInference | None:
    cfg = get_settings()
    rel = cfg.kt_subject_dirs.get(code.upper())
    if rel is None:
        return None
    path = Path(rel)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    try:
        with _lock:
            model = KTInference.from_artifacts(path, cfg.kt_model)
        logger.info("kt model loaded for %s: %s from %s", code, cfg.kt_model, path)
        return model
    except (FileNotFoundError, KeyError, OSError) as exc:
        logger.warning("kt model for %s unavailable (%s): observed performance only", code, exc)
        return None


def get_model(code: str = DEFAULT_CODE) -> KTInference | None:
    return _load((code or DEFAULT_CODE).upper())


def load_all() -> None:
    for code in get_settings().kt_subject_dirs:
        get_model(code)


def reset_cache() -> None:
    _load.cache_clear()


def info(code: str = DEFAULT_CODE) -> ModelInfo:
    m = get_model(code)
    if m is None:
        return ModelInfo(available=False, reason="Model artifacts not found on the server.")
    tm = m.meta.get("test_metrics") or {}
    return ModelInfo(
        available=True,
        name=m.name,
        display_name=m.meta.get("display_name"),
        test_auc=tm.get("AUC"),
        test_accuracy=tm.get("Accuracy"),
        parameters=m.meta.get("parameters"),
    )


def history(db: Session, user_id: uuid.UUID, subject_id: int) -> list[Attempt]:
    """The student's answers in this subject, in time order, in the model's input convention."""
    rows = db.execute(
        select(
            Interaction.item_id,
            Interaction.skill_id,
            Interaction.model_label,
            Interaction.hint_used,
            Interaction.saw_answer,
            Interaction.created_at,
            Item.n_skills,
        )
        .join(Item, Item.id == Interaction.item_id)
        .where(Interaction.user_id == user_id, Item.subject_id == subject_id)
        .order_by(Interaction.created_at, Interaction.id)
    ).all()
    multi = engine.item_skills(db, {r[0] for r in rows if r[6] > 1})
    out, prev = [], None
    for item_id, skill_id, label, hint, saw, ts, _ in rows:
        gap = (ts - prev).total_seconds() if prev is not None else 0.0
        skills = multi.get(item_id, [skill_id])
        out.append(Attempt(item_id, skills, bool(label), int(hint), bool(saw), gap))
        prev = ts
    return out


def _marker(db: Session, user_id: uuid.UUID, subject_id: int) -> tuple:
    """Changes whenever the student's history in the subject changes (new answer, regrade)."""
    n, last, labels = db.execute(
        select(func.count(), func.max(Interaction.id), func.count().filter(Interaction.model_label))
        .select_from(Interaction)
        .join(Item, Item.id == Interaction.item_id)
        .where(Interaction.user_id == user_id, Item.subject_id == subject_id)
    ).one()
    return (int(n or 0), last, int(labels or 0))


def state_for(
    db: Session, user_id: uuid.UUID, subject_id: int, code: str = DEFAULT_CODE
) -> np.ndarray | None:
    """The model's hidden state after the student's history in the subject.

    Cached per request (on the DB session) and per (user, subject, history marker), so
    refreshing states and choosing a question in the same request run the LSTM once.
    """
    m = get_model(code)
    if m is None:
        return None
    cache: dict = db.info.setdefault("kt_state_cache", {})
    key = (user_id, subject_id, _marker(db, user_id, subject_id))
    if key not in cache:
        cache[key] = m.state(history(db, user_id, subject_id))
    return cache[key]


def predict_items(
    h: np.ndarray | None,
    items: list[Item],
    skills: dict[int, list[int]] | None = None,
    code: str = DEFAULT_CODE,
) -> list[float | None]:
    """P(correct) for each item, or None when there is no model or no history yet.
    `skills` gives multi-skill questions all their skills (else the primary skill is used)."""
    m = get_model(code)
    if m is None or h is None or not items:
        return [None] * len(items)
    skills = skills or {}
    pairs = [(i.id, skills.get(i.id, [i.skill_id])) for i in items]
    return [float(p) for p in m.predict_questions(h, pairs)]


def skill_predictions(
    db: Session,
    user_id: uuid.UUID,
    subject_id: int,
    code: str = DEFAULT_CODE,
    h: np.ndarray | None = None,
) -> dict[int, float]:
    """Mean predicted success over each available skill's usable questions in the subject.

    This is a model estimate for "a typical question in this skill", NOT verified mastery.
    Empty when the model is unavailable or the student has no history in the subject yet.
    """
    m = get_model(code)
    if m is None:
        return {}
    if h is None:
        h = state_for(db, user_id, subject_id, code)
    if h is None:
        return {}
    items = db.execute(
        select(Item.id, Item.skill_id)
        .join(Skill, Skill.id == Item.skill_id)
        .where(
            Skill.subject_id == subject_id,
            Skill.is_available,
            Item.is_active,
            Item.exclusion_reason.is_(None),
            Item.n_skills == 1,
        )
    ).all()
    if not items:
        return {}
    p = m.predict_questions(h, [(iid, [sid]) for iid, sid in items])
    sums: dict[int, list[float]] = {}
    for (_, sid), pi in zip(items, p, strict=True):
        sums.setdefault(sid, []).append(float(pi))
    return {sid: float(np.mean(v)) for sid, v in sums.items()}
