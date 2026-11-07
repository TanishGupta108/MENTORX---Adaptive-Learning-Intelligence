"""Exploratory statistics on a canonical interaction table. Pure functions, no plotting."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _quantiles(s: pd.Series, qs=(0.1, 0.25, 0.5, 0.75, 0.9, 0.99)) -> dict[str, float]:
    return {f"p{int(q * 100)}": float(s.quantile(q)) for q in qs}


def summary(df: pd.DataFrame) -> dict:
    per_student = df.groupby("student_id").size()
    per_concept = df.groupby("concept_id").size()
    per_item = df.groupby("item_id").size()
    rt = df["response_ms"].dropna()
    return {
        "interactions": int(len(df)),
        "students": int(df["student_id"].nunique()),
        "items": int(df["item_id"].nunique()),
        "concepts": int(df["concept_id"].nunique()),
        "correct_rate": float(df["correct"].mean()),
        "has_timestamps": bool(df["timestamp"].notna().any()),
        "interactions_per_student": {**_quantiles(per_student), "mean": float(per_student.mean())},
        "interactions_per_concept": {**_quantiles(per_concept), "mean": float(per_concept.mean())},
        "interactions_per_item": {**_quantiles(per_item), "mean": float(per_item.mean())},
        "students_with_lt_5_interactions": int((per_student < 5).sum()),
        "items_with_lt_5_interactions": int((per_item < 5).sum()),
        "response_ms_missing_rate": float(df["response_ms"].isna().mean()),
        "response_ms": _quantiles(rt) if len(rt) else {},
    }


def _wilson(k: np.ndarray, n: np.ndarray, z: float = 1.96) -> tuple[np.ndarray, np.ndarray]:
    """95% Wilson score interval for a proportion k/n."""
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return centre - half, centre + half


def opportunity_index(df: pd.DataFrame) -> pd.Series:
    """1-based count of how many times the student has now practised this concept."""
    return df.groupby(["student_id", "concept_id"], sort=False).cumcount() + 1


def learning_curve(df: pd.DataFrame, max_opportunity: int = 20) -> pd.DataFrame:
    """P(correct) at the k-th practice opportunity on a concept, pooled over students."""
    opp = opportunity_index(df)
    g = df.assign(opportunity=opp)
    g = g[g["opportunity"] <= max_opportunity]
    curve = g.groupby("opportunity")["correct"].agg(n="size", k="sum").reset_index()
    curve["p_correct"] = curve["k"] / curve["n"]
    curve["ci_low"], curve["ci_high"] = _wilson(curve["k"].to_numpy(), curve["n"].to_numpy())
    return curve


def conditional_on_previous(df: pd.DataFrame) -> pd.DataFrame:
    """P(correct) given the previous outcome on the same concept (or none: first attempt)."""
    prev = df.groupby(["student_id", "concept_id"], sort=False)["correct"].shift(1)
    label = prev.map({1: "previous correct", 0: "previous incorrect"}).fillna("first attempt")
    out = df.assign(previous=label).groupby("previous")["correct"].agg(n="size", k="sum")
    out["p_correct"] = out["k"] / out["n"]
    out["ci_low"], out["ci_high"] = _wilson(out["k"].to_numpy(), out["n"].to_numpy())
    return out.reset_index()


def entity_accuracy(df: pd.DataFrame, by: str, min_n: int = 10) -> pd.Series:
    """Per-student or per-item correct rate, for entities with at least min_n interactions."""
    g = df.groupby(by)["correct"].agg(["mean", "size"])
    return g.loc[g["size"] >= min_n, "mean"]


def rapid_responses(df: pd.DataFrame, threshold_ms: float = 3000) -> dict:
    """Share and accuracy of answers faster than threshold_ms (possible rapid guessing)."""
    rt = df.dropna(subset=["response_ms"])
    fast = rt["response_ms"] < threshold_ms
    return {
        "threshold_ms": threshold_ms,
        "share_fast": float(fast.mean()),
        "p_correct_fast": float(rt.loc[fast, "correct"].mean()),
        "p_correct_rest": float(rt.loc[~fast, "correct"].mean()),
        "n_fast": int(fast.sum()),
    }


def response_time_by_correctness(df: pd.DataFrame) -> pd.DataFrame:
    rt = df.dropna(subset=["response_ms"])
    out = rt.groupby("correct")["response_ms"].median().rename("median_ms").reset_index()
    out["correct"] = out["correct"].map({1: "correct", 0: "incorrect"})
    return out
