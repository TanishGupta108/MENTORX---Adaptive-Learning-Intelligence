"""Candidate models behind one interface: fit(frame, X, y) and predict(frame, X) -> P(correct).

`frame` is the canonical interaction table (needed by sequence models like BKT);
`X` is the feature matrix from features.build_matrix (used by the classifiers).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from mentorx_ml.bkt import BKT


class Model:
    name: str = "model"
    params: dict[str, Any]

    def fit(self, frame: pd.DataFrame, X: pd.DataFrame, y: np.ndarray) -> Model:
        raise NotImplementedError

    def predict(self, frame: pd.DataFrame, X: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError


@dataclass
class PriorModel(Model):
    """Predicts the training-set correct rate for everyone. The floor every model must beat."""

    name: str = "prior"
    params: dict[str, Any] = field(default_factory=dict)
    p: float = 0.5

    def fit(self, frame, X, y):
        self.p = float(np.mean(y))
        return self

    def predict(self, frame, X):
        return np.full(len(X), self.p)


@dataclass
class HeuristicModel(Model):
    """Smoothed accuracy on the concept so far: (k + 1) / (n + 2). No training.

    Kept as a simple reference point. It was originally planned as MENTORX's fallback,
    but M4 showed it is badly calibrated, so FR-KT-06 now falls back to logistic regression.
    """

    name: str = "heuristic"
    params: dict[str, Any] = field(default_factory=dict)

    def fit(self, frame, X, y):
        return self

    def predict(self, frame, X):
        return X["acc_concept"].to_numpy()


@dataclass
class LogisticModel(Model):
    name: str = "logistic_regression"
    params: dict[str, Any] = field(default_factory=lambda: {"C": 1.0})
    pipeline: Any = None

    def fit(self, frame, X, y):
        self.pipeline = make_pipeline(
            StandardScaler(), LogisticRegression(C=self.params["C"], max_iter=2000)
        )
        self.pipeline.fit(X, y)
        return self

    def predict(self, frame, X):
        return self.pipeline.predict_proba(X)[:, 1]

    def coefficients(self, feature_names: list[str]) -> pd.Series:
        lr = self.pipeline[-1]
        return pd.Series(lr.coef_[0], index=feature_names).sort_values(key=np.abs, ascending=False)


@dataclass
class GradientBoostingModel(Model):
    """Histogram gradient-boosted trees (scikit-learn's LightGBM-style implementation)."""

    name: str = "gradient_boosting"
    params: dict[str, Any] = field(
        default_factory=lambda: {"learning_rate": 0.1, "max_leaf_nodes": 31}
    )
    clf: Any = None

    def fit(self, frame, X, y):
        self.clf = HistGradientBoostingClassifier(
            learning_rate=self.params["learning_rate"],
            max_leaf_nodes=self.params["max_leaf_nodes"],
            max_iter=500,
            early_stopping=True,  # stops on an internal 10% slice of the TRAINING data
            validation_fraction=0.1,
            n_iter_no_change=20,
            random_state=0,
        )
        self.clf.fit(X, y)
        return self

    def predict(self, frame, X):
        return self.clf.predict_proba(X)[:, 1]


@dataclass
class BKTModel(Model):
    name: str = "bkt"
    params: dict[str, Any] = field(default_factory=dict)
    bkt: BKT | None = None

    def fit(self, frame, X, y):
        self.bkt = BKT().fit(frame)
        return self

    def predict(self, frame, X):
        return self.bkt.predict(frame)


def grid(name: str, spec: dict[str, list]) -> list[Model]:
    """All parameter combinations for one model type."""
    import itertools

    factories = {
        "prior": PriorModel,
        "heuristic": HeuristicModel,
        "logistic_regression": LogisticModel,
        "gradient_boosting": GradientBoostingModel,
        "bkt": BKTModel,
    }
    keys = list(spec)
    combos = [dict(zip(keys, vals, strict=True)) for vals in itertools.product(*spec.values())]
    return [factories[name](params=c) for c in (combos or [{}])]
