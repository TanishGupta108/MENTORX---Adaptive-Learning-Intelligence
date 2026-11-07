"""Bayesian Knowledge Tracing (Corbett & Anderson, 1994), standard 4-parameter version.

For each concept, a student is either in the "learned" state or not:
    p_init  P(learned before the first attempt)
    p_learn P(not learned -> learned after each attempt)
    p_guess P(correct | not learned)
    p_slip  P(incorrect | learned)

The prediction for attempt t uses only attempts 1..t-1 (forward filtering), so it is
leakage-free. Parameters are fitted per concept by maximising the likelihood of the
training sequences (L-BFGS-B with bounds). Concepts with too little training data
fall back to parameters fitted on all concepts pooled. No forgetting in this version.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize

logger = logging.getLogger(__name__)

# Bounds keep the model identifiable: guess and slip above 0.3 would let the
# "learned" and "not learned" states swap meaning.
BOUNDS = [(0.01, 0.99), (0.001, 0.5), (0.01, 0.3), (0.01, 0.3)]
START = np.array([0.4, 0.1, 0.2, 0.1])
EPS = 1e-6


def _padded(seqs: list[np.ndarray], max_len: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    length = max(len(s) for s in seqs)
    if max_len:
        length = min(length, max_len)
    obs = np.zeros((len(seqs), length))
    mask = np.zeros((len(seqs), length), dtype=bool)
    for i, s in enumerate(seqs):
        n = min(len(s), length)
        obs[i, :n] = s[:n]
        mask[i, :n] = True
    return obs, mask


def forward(params: np.ndarray, obs: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """P(correct) at each step given only the previous steps. Shape = obs.shape."""
    p_init, p_learn, p_guess, p_slip = params
    known = np.full(obs.shape[0], p_init)
    pred = np.zeros_like(obs)
    for t in range(obs.shape[1]):
        p_correct = known * (1 - p_slip) + (1 - known) * p_guess
        pred[:, t] = p_correct
        o = obs[:, t]
        post = np.where(
            o == 1,
            known * (1 - p_slip) / np.maximum(p_correct, EPS),
            known * p_slip / np.maximum(1 - p_correct, EPS),
        )
        updated = post + (1 - post) * p_learn
        known = np.where(mask[:, t], updated, known)
    return pred


def neg_log_likelihood(params: np.ndarray, obs: np.ndarray, mask: np.ndarray) -> float:
    p = np.clip(forward(params, obs, mask), EPS, 1 - EPS)
    ll = obs * np.log(p) + (1 - obs) * np.log(1 - p)
    return float(-(ll[mask]).sum())


def fit_params(seqs: list[np.ndarray], max_len: int = 200) -> np.ndarray:
    obs, mask = _padded(seqs, max_len)
    res = minimize(neg_log_likelihood, START, args=(obs, mask), method="L-BFGS-B", bounds=BOUNDS)
    return res.x


def _sequences(df: pd.DataFrame) -> pd.Series:
    """Outcome arrays per (student, concept), in time order. df must be sorted by student/seq."""
    return df.groupby(["concept_id", "student_id"], sort=False)["correct"].apply(
        lambda s: s.to_numpy(dtype=float)
    )


@dataclass
class BKT:
    min_interactions: int = 50
    max_len: int = 200
    global_params: np.ndarray = field(default_factory=lambda: START.copy())
    params: dict = field(default_factory=dict)

    def fit(self, df: pd.DataFrame) -> BKT:
        seqs = _sequences(df)
        # pooled fit on a sample of sequences, used for sparse or unseen concepts
        rng = np.random.default_rng(0)
        all_seqs = list(seqs.to_numpy())
        sample = [all_seqs[i] for i in rng.choice(len(all_seqs), min(3000, len(all_seqs)), False)]
        self.global_params = fit_params(sample, self.max_len)
        for concept, group in seqs.groupby(level=0, sort=False):
            arrays = list(group.to_numpy())
            if sum(len(a) for a in arrays) < self.min_interactions:
                continue
            self.params[concept] = fit_params(arrays, self.max_len)
        logger.info("BKT: fitted %d concepts (+ global fallback)", len(self.params))
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """P(correct) for every row of a canonical frame sorted by (student_id, seq)."""
        out = np.zeros(len(df))
        pos = pd.Series(np.arange(len(df)), index=df.index)
        for concept, rows in df.groupby("concept_id", sort=False):
            params = self.params.get(concept, self.global_params)
            groups = rows.groupby("student_id", sort=False)
            seqs = [g["correct"].to_numpy(dtype=float) for _, g in groups]
            idx = [pos[g.index].to_numpy() for _, g in groups]
            obs, mask = _padded(seqs)
            pred = forward(params, obs, mask)
            for i, rows_idx in enumerate(idx):
                out[rows_idx] = pred[i, : len(rows_idx)]
        return out

    def params_table(self) -> pd.DataFrame:
        names = ("p_init", "p_learn", "p_guess", "p_slip")
        rows = [
            {"concept_id": c, **dict(zip(names, p, strict=True))} for c, p in self.params.items()
        ]
        return pd.DataFrame(rows)
