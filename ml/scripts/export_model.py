"""Export trained models as a serving bundle for the backend.

Usage (from ml/):
    python scripts/export_model.py --config configs/ednet.yaml --version v1 \
        --out ../backend/model_artifacts

Writes, for the experiment's selected model and its logistic-regression fallback:
    <name>.joblib   {"estimator", "features", "use_time"} (plain scikit-learn objects)
    manifest.json   names, types, SHA-256 checksums, features, library versions,
                    training data, validation + test metrics, and the constant prior
The backend verifies every checksum and feature list before using a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import sklearn

from mentorx_ml.experiment import artifact_dir, experiment_name, load_config, report_dir

TYPE = {"gradient_boosting": "gbm", "logistic_regression": "logreg"}


def _estimator(model):
    if hasattr(model, "clf"):
        return model.clf
    if hasattr(model, "pipeline"):
        return model.pipeline
    raise ValueError(f"{type(model).__name__} can't be exported for serving")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--version", required=True, help="e.g. v1")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    cfg = load_config(args.config)
    exp = experiment_name(cfg)
    sel = json.loads((report_dir(cfg) / "selection.json").read_text(encoding="utf-8"))
    test = json.loads((report_dir(cfg) / "test_metrics.json").read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)

    names = [sel["chosen"]] + (
        ["logistic_regression"] if sel["chosen"] != "logistic_regression" else []
    )
    entries = []
    for i, name in enumerate(names):
        bundle = joblib.load(artifact_dir(cfg) / f"{name}.joblib")
        payload = {
            "estimator": _estimator(bundle["model"]),
            "features": bundle["features"],
            "use_time": cfg["features"]["use_time"],
        }
        filename = f"{exp}-{TYPE[name]}-{args.version}.joblib"
        path = args.out / filename
        joblib.dump(payload, path, compress=3)
        entries.append(
            {
                "name": f"{exp}-{TYPE[name]}-{args.version}",
                "model_type": TYPE[name],
                "role": "primary" if i == 0 else "fallback",
                "file": filename,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "features": bundle["features"],
                "use_time": cfg["features"]["use_time"],
                "validation": {
                    k: sel["best_per_model"][name][k] for k in ("auc", "log_loss", "ece")
                },
                "test": {k: test["point"][name][k] for k in ("auc", "log_loss", "ece")},
            }
        )

    prior_bundle = joblib.load(artifact_dir(cfg) / "prior.joblib")
    manifest = {
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "experiment": exp,
        "training_data": f"{cfg['dataset']} (sha256 {sel['data_sha256'][:16]}…), "
        f"{sel['split_students']['train']} training students",
        "licence_note": "Trained on EdNet (CC BY-NC 4.0): non-commercial use only; attribute EdNet."
        if cfg["dataset"] == "ednet"
        else "",
        "sklearn_version": sklearn.__version__,
        "selected_at": sel["selected_at"],
        "models": entries,
        "prior": {
            "name": f"{exp}-prior-{args.version}",
            "model_type": "prior",
            "p": float(prior_bundle["model"].p),
        },
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for e in entries:
        size = (args.out / e["file"]).stat().st_size / 1e6
        print(f"{e['role']:>8}: {e['file']} ({size:.2f} MB) val AUC {e['validation']['auc']:.4f}")
    print(f"   prior: p = {manifest['prior']['p']:.4f}")


if __name__ == "__main__":
    main()
