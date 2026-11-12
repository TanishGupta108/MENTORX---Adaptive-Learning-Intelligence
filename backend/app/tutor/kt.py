"""Model serving for the tutor: load the exported knowledge-tracing model once and turn a
student's interaction log into predictions.

Kept separate from answer checking and recommendation rules (they only consume numbers).
If the artifacts are missing the service reports `available = False` and every caller
shows observed performance only. Nothing is ever labelled as a model prediction unless
it came from the real model.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ml.dkt import Attempt, KTInference
from app.tutor import engine
from app.tutor.models import Interaction, Item, Skill

logger = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[2]
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


@lru_cache
def _load() -> KTInference | None:
    cfg = get_settings()
    path = Path(cfg.kt_artifacts_dir)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    try:
        with _lock:
            model = KTInference.from_artifacts(path, cfg.kt_model)
        logger.info("kt model loaded: %s from %s", cfg.kt_model, path)
        return model
    except (FileNotFoundError, KeyError, OSError) as exc:
        logger.warning("kt model unavailable (%s): showing observed performance only", exc)
        return None


def get_model() -> KTInference | None:
    return _load()


def reset_cache() -> None:
    _load.cache_clear()


def info() -> ModelInfo:
    m = get_model()
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


def history(db: Session, user_id: uuid.UUID) -> list[Attempt]:
    """The student's answers in time order, in the model's input convention."""
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
        .where(Interaction.user_id == user_id)
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


def state_for(db: Session, user_id: uuid.UUID) -> np.ndarray | None:
    m = get_model()
    if m is None:
        return None
    return m.state(history(db, user_id))


def predict_items(
    h: np.ndarray | None, items: list[Item], skills: dict[int, list[int]] | None = None
) -> list[float | None]:
    """P(correct) for each item, or None when there is no model or no history yet.
    `skills` gives multi-skill questions all their skills (else the primary skill is used)."""
    m = get_model()
    if m is None or h is None or not items:
        return [None] * len(items)
    skills = skills or {}
    pairs = [(i.id, skills.get(i.id, [i.skill_id])) for i in items]
    return [float(p) for p in m.predict_questions(h, pairs)]


def skill_predictions(
    db: Session, user_id: uuid.UUID, h: np.ndarray | None = None
) -> dict[int, float]:
    """Mean predicted success over each available skill's usable questions.

    This is a model estimate for "a typical question in this skill", NOT verified mastery.
    Empty when the model is unavailable or the student has no history yet.
    """
    m = get_model()
    if m is None:
        return {}
    if h is None:
        h = state_for(db, user_id)
    if h is None:
        return {}
    items = db.execute(
        select(Item.id, Item.skill_id)
        .join(Skill, Skill.id == Item.skill_id)
        .where(
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
