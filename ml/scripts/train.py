"""Train every candidate model, tune on validation, and apply the pre-registered selection rule.

Usage (from ml/):  python scripts/train.py --config configs/assist2009.yaml

The TEST split is never scored here. Outputs:
  artifacts/<dataset>/<model>.joblib      fitted models (gitignored)
  reports/models/<dataset>/validation.json  every configuration's validation metrics
  reports/models/<dataset>/selection.json   the chosen model and why
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import joblib

from mentorx_ml import metrics
from mentorx_ml.experiment import (
    artifact_dir,
    latency_ms,
    load_config,
    prepare,
    report_dir,
    write_json,
)
from mentorx_ml.models import grid

log = logging.getLogger("train")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = load_config(args.config)

    t0 = time.time()
    prep = prepare(config)
    log.info(
        "Rows: train %d, val %d, test %d | features: %s",
        *(len(prep.frames[k]) for k in ("train", "val", "test")),
        prep.features,
    )

    all_results, best = [], {}
    for name, spec in config["models"].items():
        for model in grid(name, spec):
            t = time.time()
            model.fit(prep.frames["train"], prep.X["train"], prep.y["train"])
            p_val = model.predict(prep.frames["val"], prep.X["val"])
            m = metrics.compute(prep.y["val"], p_val)
            m["fit_seconds"] = round(time.time() - t, 1)
            m["latency_ms_50"] = latency_ms(model, prep.frames["val"], prep.X["val"])
            all_results.append({"model": name, "params": model.params, **m})
            log.info(
                "%s %s val log_loss=%.4f auc=%.4f ece=%.4f",
                name,
                model.params,
                m["log_loss"],
                m["auc"],
                m["ece"],
            )
            if name not in best or m["log_loss"] < best[name][1]["log_loss"]:
                best[name] = (model, m)

    # ---- pre-registered selection rule -------------------------------------------------
    rule = config["selection"]
    eligible, rejected = [], {}
    for name, (_, m) in best.items():
        if name in rule["exclude"]:
            continue
        reasons = []
        if m["ece"] > rule["max_ece"]:
            reasons.append(f"ECE {m['ece']:.3f} > {rule['max_ece']}")
        if m["latency_ms_50"] > rule["max_latency_ms_50_candidates"]:
            reasons.append(f"latency {m['latency_ms_50']:.1f} ms > limit")
        (rejected.__setitem__(name, reasons) if reasons else eligible.append(name))
    if not eligible:
        raise SystemExit(f"No model passed the selection rule: {rejected}")
    chosen = min(eligible, key=lambda n: best[n][1][rule["metric"]])

    out_art = artifact_dir(config)
    out_art.mkdir(parents=True, exist_ok=True)
    for name, (model, _) in best.items():
        joblib.dump(
            {
                "model": model,
                "features": prep.features,
                "difficulty": prep.difficulty,
                "config": config,
                "data_sha256": prep.data_sha256,
            },
            out_art / f"{name}.joblib",
        )

    out_rep = report_dir(config)
    write_json(out_rep / "validation.json", all_results)
    write_json(
        out_rep / "selection.json",
        {
            "selected_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "rule": rule,
            "chosen": chosen,
            "chosen_params": best[chosen][0].params,
            "best_per_model": {n: {"params": mm.params, **m} for n, (mm, m) in best.items()},
            "eligible": eligible,
            "rejected": rejected,
            "features": prep.features,
            "data_sha256": prep.data_sha256,
            "split_rows": {k: len(v) for k, v in prep.frames.items()},
            "split_students": {k: int(v["student_id"].nunique()) for k, v in prep.frames.items()},
        },
    )
    log.info(
        "Selected %s (val %s=%.4f). Total %.0fs",
        chosen,
        rule["metric"],
        best[chosen][1][rule["metric"]],
        time.time() - t0,
    )


if __name__ == "__main__":
    main()
