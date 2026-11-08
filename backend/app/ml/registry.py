"""Load the active knowledge model, with a verified fallback chain (FR-KT-05, FR-KT-06).

Order: active model in `model_versions` -> logistic-regression fallback -> constant prior.
Every artifact is checked before use: SHA-256 matches the manifest, scikit-learn version
matches, feature list matches, and it produces sane probabilities on a test row.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ModelVersion

logger = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[2]


@dataclass
class LoadedModel:
    version_id: int
    name: str
    model_type: str
    features: list[str]
    use_time: bool
    estimator: object | None = None  # None for the constant prior
    prior_p: float | None = None

    @property
    def is_ml(self) -> bool:
        return self.estimator is not None

    def predict(self, rows: list[dict[str, float]]) -> np.ndarray:
        if not rows:
            return np.zeros(0)
        if self.estimator is None:
            return np.full(len(rows), self.prior_p)
        # Named columns: the estimator was fitted on a DataFrame and checks names and order.
        X = pd.DataFrame([[r[f] for f in self.features] for r in rows], columns=self.features)
        return self.estimator.predict_proba(X.astype(float))[:, 1]


class ArtifactError(RuntimeError):
    pass


def _artifacts_dir() -> Path:
    d = Path(get_settings().model_artifacts_dir)
    return d if d.is_absolute() else BACKEND_DIR / d


def load_manifest() -> dict:
    return json.loads((_artifacts_dir() / "manifest.json").read_text(encoding="utf-8"))


def sync_model_versions(db: Session) -> None:
    """Register the bundled artifacts in model_versions. Activates the primary if none is active."""
    manifest = load_manifest()
    existing = {m.name: m for m in db.scalars(select(ModelVersion))}
    entries = [
        {
            **m,
            "artifact_path": m["file"],
            "metrics": {"validation": m["validation"], "test": m["test"]},
        }
        for m in manifest["models"]
    ] + [
        {
            **manifest["prior"],
            "artifact_path": None,
            "sha256": None,
            "features": [],
            "metrics": {"p": manifest["prior"]["p"]},
        }
    ]
    for e in entries:
        row = existing.get(e["name"]) or ModelVersion(name=e["name"])
        row.model_type = e["model_type"]
        row.artifact_path = e["artifact_path"]
        row.artifact_sha256 = e["sha256"]
        row.feature_names = e["features"]
        row.metrics = e["metrics"]
        row.training_data = manifest["training_data"][:200]
        db.add(row)
    db.flush()
    if db.scalar(select(ModelVersion).where(ModelVersion.is_active)) is None:
        primary = next(m for m in manifest["models"] if m["role"] == "primary")
        db.execute(
            update(ModelVersion).where(ModelVersion.name == primary["name"]).values(is_active=True)
        )
    db.commit()


def _load_artifact(row: ModelVersion, entry: dict, sklearn_version: str) -> LoadedModel:
    if sklearn_version != sklearn.__version__:
        raise ArtifactError(
            f"saved with scikit-learn {sklearn_version}, running {sklearn.__version__}"
        )
    path = _artifacts_dir() / entry["file"]
    if not path.exists():
        raise ArtifactError(f"{path.name} missing")
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise ArtifactError(f"{path.name} checksum mismatch")
    payload = joblib.load(path)
    if payload["features"] != entry["features"]:
        raise ArtifactError(f"{path.name} feature list differs from manifest")
    model = LoadedModel(
        row.id,
        row.name,
        row.model_type,
        payload["features"],
        payload["use_time"],
        estimator=payload["estimator"],
    )
    p = model.predict([dict.fromkeys(model.features, 0.0)])
    if not (len(p) == 1 and 0.0 < p[0] < 1.0):
        raise ArtifactError(f"{path.name} smoke prediction out of range: {p}")
    return model


def load_active(db: Session) -> LoadedModel:
    """Return the best model that loads and passes every check."""
    manifest = load_manifest()
    entries = {m["name"]: m for m in manifest["models"]}
    rows = {m.name: m for m in db.scalars(select(ModelVersion))}
    active = db.scalar(select(ModelVersion).where(ModelVersion.is_active))
    fallback = next((m["name"] for m in manifest["models"] if m["role"] == "fallback"), None)

    for name in [active.name if active else None, fallback]:
        if not name or name not in entries or name not in rows:
            continue
        try:
            model = _load_artifact(rows[name], entries[name], manifest["sklearn_version"])
            if active is None or name != active.name:
                logger.error("Active model unavailable; using fallback %s", name)
            logger.info("Knowledge model loaded: %s", name)
            return model
        except Exception as exc:  # any failure -> try the next model (FR-KT-06)
            logger.error("Model %s failed to load: %s", name, exc)

    prior = manifest["prior"]
    logger.error("No ML model available; using constant prior %.3f", prior["p"])
    return LoadedModel(
        rows[prior["name"]].id, prior["name"], "prior", [], False, prior_p=prior["p"]
    )


_cached: LoadedModel | None = None


def get_model(db: Session) -> LoadedModel:
    global _cached
    if _cached is None:
        sync_model_versions(db)
        _cached = load_active(db)
    return _cached


def reset_cache() -> None:
    global _cached
    _cached = None
