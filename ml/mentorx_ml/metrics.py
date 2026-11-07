"""Evaluation metrics for probabilistic binary predictions."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, brier_score_loss, f1_score, log_loss, roc_auc_score

EPS = 1e-6


def expected_calibration_error(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> float:
    """Weighted mean |observed rate - mean prediction| over equal-width probability bins."""
    bins = np.clip((p * n_bins).astype(int), 0, n_bins - 1)
    ece = 0.0
    for b in range(n_bins):
        mask = bins == b
        if mask.any():
            ece += mask.mean() * abs(y[mask].mean() - p[mask].mean())
    return float(ece)


def reliability_table(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    bins = np.clip((p * n_bins).astype(int), 0, n_bins - 1)
    df = pd.DataFrame({"bin": bins, "y": y, "p": p})
    out = df.groupby("bin").agg(mean_pred=("p", "mean"), observed=("y", "mean"), n=("y", "size"))
    return out.reset_index()


def compute(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    y = np.asarray(y, dtype=int)
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    pred = (p >= 0.5).astype(int)
    return {
        "auc": float(roc_auc_score(y, p)),
        "accuracy": float(accuracy_score(y, pred)),
        "f1": float(f1_score(y, pred)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "brier": float(brier_score_loss(y, p)),
        "ece": expected_calibration_error(y, p),
        "n": int(len(y)),
    }


def bootstrap_by_student(
    students: np.ndarray,
    y: np.ndarray,
    preds: dict[str, np.ndarray],
    n_boot: int = 200,
    seed: int = 0,
    metrics: tuple[str, ...] = ("auc", "log_loss", "accuracy", "f1", "brier", "ece"),
    reference: str | None = None,
) -> dict[str, dict[str, tuple[float, float]]]:
    """95% percentile CIs, resampling whole students (their rows are not independent).

    All models are scored on the SAME resamples. If `reference` names one of the models,
    CIs for each model's AUC and log-loss difference against it are returned under the
    keys "delta_auc" and "delta_log_loss" (positive delta_auc / negative delta_log_loss
    = better than the reference).
    """
    rng = np.random.default_rng(seed)
    codes, uniq = pd.factorize(students)
    rows_of = pd.Series(np.arange(len(codes))).groupby(codes).apply(np.asarray).to_list()
    names = list(preds)
    keys = list(metrics) + (["delta_auc", "delta_log_loss"] if reference else [])
    samples: dict[str, dict[str, list[float]]] = {m: {k: [] for k in keys} for m in names}
    for _ in range(n_boot):
        pick = rng.integers(0, len(uniq), len(uniq))
        idx = np.concatenate([rows_of[i] for i in pick])
        if y[idx].min() == y[idx].max():
            continue
        results = {m: compute(y[idx], preds[m][idx]) for m in names}
        for m in names:
            for k in metrics:
                samples[m][k].append(results[m][k])
            if reference:
                samples[m]["delta_auc"].append(results[m]["auc"] - results[reference]["auc"])
                samples[m]["delta_log_loss"].append(
                    results[m]["log_loss"] - results[reference]["log_loss"]
                )
    return {
        m: {k: (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))) for k, v in d.items()}
        for m, d in samples.items()
    }
