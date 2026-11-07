"""Feature engineering for P(correct) prediction.

Two kinds of features:
1. History features: computed for each row from that student's STRICTLY EARLIER rows
   only (every series is shifted by one before aggregating). No other student's data
   is used, so these are leakage-free by construction.
2. Difficulty features: how hard an item / concept is, estimated from TRAINING
   students only. For training rows themselves, the estimate is cross-fitted
   (out-of-fold by student), so a row's own label never contributes to its feature.

All features are concept-agnostic (no concept or item IDs are features), so a model
trained on one dataset can be applied to MENTORX's questions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

LAST_K_CONCEPT = 3
LAST_K_OVERALL = 10

HISTORY_FEATURES = [
    "log_prior_concept",  # log(1 + attempts on this concept so far)
    "acc_concept",  # smoothed accuracy on this concept so far: (k + 1) / (n + 2)
    "acc_concept_last3",  # smoothed accuracy over the last 3 attempts on the concept
    "prev_concept",  # previous outcome on concept: +1 correct, -1 incorrect, 0 none
    "is_first_concept",  # 1 if this is the first attempt on the concept
    "log_gap_concept",  # log(1 + other interactions since last attempt on the concept)
    "log_prior_overall",  # log(1 + all attempts so far)
    "acc_overall",  # smoothed overall accuracy so far
    "acc_overall_last10",  # smoothed accuracy over the last 10 attempts
    "log_prior_item",  # log(1 + previous attempts at this exact item)
    "prev_item_correct",  # 1 if a previous attempt at this item was correct
]
TIME_FEATURES = [
    "log_secs_since_concept",  # log(1 + seconds since last attempt on the concept)
    "log_secs_since_any",  # log(1 + seconds since the previous interaction)
]
DIFFICULTY_FEATURES = ["item_logit", "concept_logit", "log_item_count"]


def feature_names(use_time: bool) -> list[str]:
    return HISTORY_FEATURES + (TIME_FEATURES if use_time else []) + DIFFICULTY_FEATURES


def _smoothed(k, n):
    return (k + 1.0) / (n + 2.0)


def _last_k(grouped_correct, k: int) -> tuple[pd.Series, pd.Series]:
    """Sum and count of the previous k outcomes within each group (excluding the current row)."""
    shifted = [grouped_correct.shift(i) for i in range(1, k + 1)]
    stacked = pd.concat(shifted, axis=1)
    return stacked.sum(axis=1, min_count=0), stacked.notna().sum(axis=1)


def history_features(df: pd.DataFrame, use_time: bool) -> pd.DataFrame:
    """History features for every row of a canonical frame sorted by (student_id, seq)."""
    out = pd.DataFrame(index=df.index)
    correct = df["correct"].astype("float64")

    by_student = df.groupby("student_id", sort=False)
    by_concept = df.groupby(["student_id", "concept_id"], sort=False)
    by_item = df.groupby(["student_id", "item_id"], sort=False)

    # concept history
    n_c = by_concept.cumcount()
    k_c = by_concept["correct"].cumsum() - df["correct"]
    out["log_prior_concept"] = np.log1p(n_c)
    out["acc_concept"] = _smoothed(k_c, n_c)
    gc = correct.groupby([df["student_id"], df["concept_id"]], sort=False)
    s3, c3 = _last_k(gc, LAST_K_CONCEPT)
    out["acc_concept_last3"] = _smoothed(s3, c3)
    prev_c = gc.shift(1)
    out["prev_concept"] = prev_c.map({1.0: 1.0, 0.0: -1.0}).fillna(0.0)
    out["is_first_concept"] = (n_c == 0).astype("float64")
    prev_seq_c = df.groupby(["student_id", "concept_id"], sort=False)["seq"].shift(1)
    gap = (df["seq"] - prev_seq_c - 1).fillna(0)
    out["log_gap_concept"] = np.log1p(gap)

    # overall history
    n_all = by_student.cumcount()
    k_all = by_student["correct"].cumsum() - df["correct"]
    out["log_prior_overall"] = np.log1p(n_all)
    out["acc_overall"] = _smoothed(k_all, n_all)
    gs = correct.groupby(df["student_id"], sort=False)
    s10, c10 = _last_k(gs, LAST_K_OVERALL)
    out["acc_overall_last10"] = _smoothed(s10, c10)

    # same-item history
    n_i = by_item.cumcount()
    k_i = by_item["correct"].cumsum() - df["correct"]
    out["log_prior_item"] = np.log1p(n_i)
    out["prev_item_correct"] = (k_i > 0).astype("float64")

    if use_time:
        ts = df["timestamp"]
        if ts.isna().all():
            raise ValueError("use_time=True but the dataset has no timestamps")
        prev_t_c = df.groupby(["student_id", "concept_id"], sort=False)["timestamp"].shift(1)
        prev_t_any = by_student["timestamp"].shift(1)
        secs_c = (ts - prev_t_c).dt.total_seconds().clip(lower=0).fillna(0)
        secs_any = (ts - prev_t_any).dt.total_seconds().clip(lower=0).fillna(0)
        out["log_secs_since_concept"] = np.log1p(secs_c)
        out["log_secs_since_any"] = np.log1p(secs_any)

    return out


def _logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


@dataclass
class DifficultyTable:
    """Smoothed item and concept correct rates, learned from training students.

    item_p = (k_item + m * p_concept) / (n_item + m): an item with few attempts is
    pulled towards its concept's average, which is pulled towards the global average.
    """

    m_item: float = 10.0
    m_concept: float = 20.0
    global_p: float = 0.5
    concept_p: dict = field(default_factory=dict)
    item_p: dict = field(default_factory=dict)
    item_n: dict = field(default_factory=dict)

    def fit(self, df: pd.DataFrame) -> DifficultyTable:
        self.global_p = float(df["correct"].mean())
        c = df.groupby("concept_id")["correct"].agg(["sum", "size"])
        cp = (c["sum"] + self.m_concept * self.global_p) / (c["size"] + self.m_concept)
        self.concept_p = cp.to_dict()
        i = df.groupby(["item_id", "concept_id"])["correct"].agg(["sum", "size"]).reset_index()
        prior = i["concept_id"].map(self.concept_p).fillna(self.global_p)
        i["p"] = (i["sum"] + self.m_item * prior) / (i["size"] + self.m_item)
        self.item_p = dict(zip(i["item_id"], i["p"], strict=True))
        self.item_n = dict(zip(i["item_id"], i["size"], strict=True))
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        concept_p = df["concept_id"].map(self.concept_p).astype("float64").fillna(self.global_p)
        item_p = df["item_id"].map(self.item_p).astype("float64").fillna(concept_p)
        item_n = df["item_id"].map(self.item_n).astype("float64").fillna(0)
        return pd.DataFrame(
            {
                "item_logit": _logit(item_p.to_numpy()),
                "concept_logit": _logit(concept_p.to_numpy()),
                "log_item_count": np.log1p(item_n.to_numpy()),
            },
            index=df.index,
        )


def difficulty_features(
    train: pd.DataFrame, other: list[pd.DataFrame], n_folds: int = 5, seed: int = 0
) -> tuple[pd.DataFrame, list[pd.DataFrame], DifficultyTable]:
    """Cross-fitted difficulty for train rows; full-train table for the other frames."""
    train_feats = pd.DataFrame(index=train.index, columns=DIFFICULTY_FEATURES, dtype="float64")
    students = train["student_id"].to_numpy()
    # Shuffle student groups deterministically so folds don't follow ID order.
    rng = np.random.default_rng(seed)
    uniq = np.unique(students)
    perm = dict(zip(uniq, rng.permutation(len(uniq)), strict=True))
    groups = np.array([perm[s] for s in students])
    for fit_idx, pred_idx in GroupKFold(n_splits=n_folds).split(train, groups=groups):
        table = DifficultyTable().fit(train.iloc[fit_idx])
        train_feats.iloc[pred_idx] = table.transform(train.iloc[pred_idx]).to_numpy()
    full = DifficultyTable().fit(train)
    return train_feats, [full.transform(o) for o in other], full


def build_matrix(
    frames: dict[str, pd.DataFrame], use_time: bool, seed: int = 0
) -> tuple[dict[str, pd.DataFrame], DifficultyTable]:
    """Features for train/val/test frames. Each frame must be canonical and sorted."""
    names = [k for k in frames if k != "train"]
    hist = {k: history_features(v, use_time) for k, v in frames.items()}
    tr_diff, other_diff, table = difficulty_features(
        frames["train"], [frames[k] for k in names], seed=seed
    )
    diff = {"train": tr_diff, **dict(zip(names, other_diff, strict=True))}
    cols = feature_names(use_time)
    out = {k: pd.concat([hist[k], diff[k]], axis=1)[cols].astype("float64") for k in frames}
    return out, table
