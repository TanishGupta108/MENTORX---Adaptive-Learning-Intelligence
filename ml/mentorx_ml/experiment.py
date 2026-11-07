"""Shared setup for train.py and evaluate.py, so both see identical splits and features."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from mentorx_ml.features import DifficultyTable, build_matrix, feature_names
from mentorx_ml.models import Model
from mentorx_ml.splits import split_by_student

ML_DIR = Path(__file__).resolve().parents[1]


@dataclass
class Prepared:
    config: dict
    frames: dict[str, pd.DataFrame]
    X: dict[str, pd.DataFrame]
    y: dict[str, np.ndarray]
    difficulty: DifficultyTable
    features: list[str]
    data_sha256: str


def load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def prepare(config: dict) -> Prepared:
    path = ML_DIR / "data" / "processed" / f"{config['dataset']}.parquet"
    if not path.exists():
        raise SystemExit(f"{path} not found. Run scripts/download.py and scripts/clean.py first.")
    data_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    df = pd.read_parquet(path)
    split = split_by_student(
        df,
        val_frac=config["split"]["val_frac"],
        test_frac=config["split"]["test_frac"],
        seed=config["seed"],
    )
    frames = {"train": split.train, "val": split.val, "test": split.test}
    use_time = config["features"]["use_time"]
    X, table = build_matrix(frames, use_time=use_time, seed=config["seed"])
    # Ablations drop feature groups, e.g. item-level difficulty that new questions lack.
    exclude = set(config["features"].get("exclude", []))
    unknown = exclude - set(feature_names(use_time))
    if unknown:
        raise ValueError(f"unknown features in exclude: {sorted(unknown)}")
    names = [f for f in feature_names(use_time) if f not in exclude]
    X = {k: v[names] for k, v in X.items()}
    y = {k: v["correct"].to_numpy(dtype=int) for k, v in frames.items()}
    return Prepared(config, frames, X, y, table, names, data_sha)


def latency_ms(model: Model, frame: pd.DataFrame, X: pd.DataFrame, n: int = 50) -> float:
    """Median wall time to score n candidate rows (model call only; features excluded)."""
    sub_f, sub_x = frame.iloc[:n], X.iloc[:n]
    times = []
    for _ in range(20):
        t0 = time.perf_counter()
        model.predict(sub_f, sub_x)
        times.append((time.perf_counter() - t0) * 1000)
    return float(np.median(times))


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=float) + "\n", encoding="utf-8")


def experiment_name(config: dict) -> str:
    return config.get("name", config["dataset"])


def report_dir(config: dict) -> Path:
    return ML_DIR / "reports" / "models" / experiment_name(config)


def artifact_dir(config: dict) -> Path:
    return ML_DIR / "artifacts" / experiment_name(config)
