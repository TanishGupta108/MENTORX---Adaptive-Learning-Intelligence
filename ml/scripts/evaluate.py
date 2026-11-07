"""Score the trained models on the held-out TEST students, once, and write the comparison report.

Usage (from ml/):  python scripts/evaluate.py --config configs/assist2009.yaml

Run train.py first. The model choice was already fixed by train.py on validation data;
this script only reports. It refuses to re-score the test set unless --force is given,
and every forced re-run is recorded in the report, so test-set peeking stays visible.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402

from mentorx_ml import metrics  # noqa: E402
from mentorx_ml.experiment import (  # noqa: E402
    artifact_dir,
    load_config,
    prepare,
    report_dir,
    write_json,
)

COLORS = {
    "prior": "#b5b5ad",
    "heuristic": "#8a8a84",
    "logistic_regression": "#e8590c",
    "gradient_boosting": "#3b5bdb",
    "bkt": "#2b8a3e",
}
LABELS = {
    "prior": "Prior (constant)",
    "heuristic": "Heuristic (smoothed concept accuracy)",
    "logistic_regression": "Logistic regression",
    "gradient_boosting": "Gradient boosting",
    "bkt": "BKT",
}


def reliability_plot(y, preds, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.2, 5))
    ax.plot([0, 1], [0, 1], ls="--", color="#c8c8c2", lw=1)
    for name, p in preds.items():
        if name == "prior":
            continue
        t = metrics.reliability_table(y, p)
        ax.plot(
            t["mean_pred"],
            t["observed"],
            marker="o",
            ms=3,
            color=COLORS.get(name),
            label=LABELS.get(name, name),
        )
    ax.set_xlabel("mean predicted P(correct)")
    ax.set_ylabel("observed fraction correct")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title("Calibration on test students", loc="left")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def fmt_ci(v, ci, digits=4):
    return f"{v:.{digits}f} ({ci[0]:.{digits}f}–{ci[1]:.{digits}f})"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--force", action="store_true", help="re-score the test set (logged)")
    args = parser.parse_args()
    config = load_config(args.config)
    out = report_dir(config)
    selection = json.loads((out / "selection.json").read_text(encoding="utf-8"))

    history_path = out / "test_evaluations.json"
    history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
    if history and not args.force:
        raise SystemExit(
            f"The test set was already scored {len(history)} time(s). Re-scoring after looking "
            "at test results risks test-set overfitting. Use --force to proceed (it will be logged)."
        )

    prep = prepare(config)
    if prep.data_sha256 != selection["data_sha256"]:
        raise SystemExit("Processed data changed since training. Re-run train.py first.")

    loaded = {
        name: joblib.load(artifact_dir(config) / f"{name}.joblib")["model"]
        for name in selection["best_per_model"]
    }
    y = prep.y["test"]
    preds = {n: m.predict(prep.frames["test"], prep.X["test"]) for n, m in loaded.items()}
    point = {n: metrics.compute(y, p) for n, p in preds.items()}
    ref = config["evaluation"]["reference_model"]
    ci = metrics.bootstrap_by_student(
        prep.frames["test"]["student_id"].to_numpy(),
        y,
        preds,
        n_boot=config["evaluation"]["bootstrap_reps"],
        seed=config["seed"],
        reference=ref,
    )

    now = datetime.now(UTC).isoformat(timespec="seconds")
    history.append({"evaluated_at": now, "chosen": selection["chosen"]})
    write_json(history_path, history)
    write_json(out / "test_metrics.json", {"evaluated_at": now, "point": point, "ci95": ci})
    reliability_plot(y, preds, out / "reliability.png")

    # Interpretability (computed on VALIDATION data, not test)
    interp: list[str] = []
    if "logistic_regression" in loaded:
        coefs = loaded["logistic_regression"].coefficients(prep.features)
        interp += [
            "### Logistic regression coefficients (standardised features)",
            "",
            "| Feature | Coefficient |",
            "|---|---:|",
        ]
        interp += [f"| `{k}` | {v:+.3f} |" for k, v in coefs.items()]
        interp.append("")
    if "gradient_boosting" in loaded:
        n = min(20000, len(prep.X["val"]))
        rng = np.random.default_rng(0)
        idx = rng.choice(len(prep.X["val"]), n, replace=False)
        clf = loaded["gradient_boosting"].clf
        imp = permutation_importance(
            clf,
            prep.X["val"].iloc[idx],
            prep.y["val"][idx],
            scoring="neg_log_loss",
            n_repeats=3,
            random_state=0,
        )
        s = pd.Series(imp.importances_mean, index=prep.features).sort_values(ascending=False)
        interp += [
            "### Gradient boosting permutation importance (increase in validation log loss)",
            "",
            "| Feature | Importance |",
            "|---|---:|",
        ]
        interp += [f"| `{k}` | {v:.4f} |" for k, v in s.items()]
        interp.append("")
    if "bkt" in loaded:
        t = loaded["bkt"].bkt.params_table()
        q = t[["p_init", "p_learn", "p_guess", "p_slip"]].quantile([0.25, 0.5, 0.75]).T
        interp += [
            f"### BKT parameters across {len(t)} concepts (quartiles)",
            "",
            "| Parameter | 25% | median | 75% |",
            "|---|---:|---:|---:|",
        ]
        interp += [
            f"| {k} | {r[0.25]:.3f} | {r[0.5]:.3f} | {r[0.75]:.3f} |" for k, r in q.iterrows()
        ]
        interp.append("")

    order = sorted(point, key=lambda n: point[n]["log_loss"])
    val = selection["best_per_model"]
    lines = [
        f"# Model comparison: {config.get('name', config['dataset'])}",
        "",
        config.get("description", "").strip(),
        "",
        "_Generated by `ml/scripts/train.py` and `ml/scripts/evaluate.py`. Do not edit by hand._",
        "",
        "## Setup",
        "",
        f"- Data: `data/processed/{config['dataset']}.parquet`, sha256 `{prep.data_sha256[:16]}…`",
        f"- Split by student (seed {config['seed']}): "
        + ", ".join(
            f"{k} {selection['split_students'][k]:,} students / {selection['split_rows'][k]:,} rows"
            for k in ("train", "val", "test")
        ),
        f"- Features ({len(prep.features)}): " + ", ".join(f"`{f}`" for f in prep.features),
        "- History features use only each student's earlier answers; difficulty features are learned "
        "from training students only (cross-fitted for training rows). Leakage tests: `ml/tests/test_features.py`.",
        "",
        "## Selection (on validation data, before the test set was scored)",
        "",
        f"Rule (pre-registered in the config): lowest validation **{selection['rule']['metric']}** among models "
        f"with ECE ≤ {selection['rule']['max_ece']} and scoring 50 candidates in ≤ "
        f"{selection['rule']['max_latency_ms_50_candidates']} ms; `prior` is a reference only.",
        "",
        "| Model | Best params | Val log loss | Val AUC | Val ECE | Latency (50) | Fit time |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for n in sorted(val, key=lambda k: val[k]["log_loss"]):
        v = val[n]
        params = ", ".join(f"{k}={p}" for k, p in v["params"].items()) or "—"
        lines.append(
            f"| {LABELS.get(n, n)} | {params} | {v['log_loss']:.4f} | {v['auc']:.4f} | "
            f"{v['ece']:.4f} | {v['latency_ms_50']:.1f} ms | {v['fit_seconds']:.0f} s |"
        )
    lines += [
        "",
        f"**Selected: {LABELS.get(selection['chosen'], selection['chosen'])}** (selected at {selection['selected_at']}).",
    ]
    if selection["rejected"]:
        lines.append(
            "Rejected by the rule: "
            + "; ".join(
                f"{LABELS.get(k, k)} ({', '.join(v)})" for k, v in selection["rejected"].items()
            )
        )
    lines += [
        "",
        f"## Test results ({len(y):,} answers from {selection['split_students']['test']:,} unseen students)",
        "",
        f"Point estimates with 95% bootstrap CIs (students resampled, {config['evaluation']['bootstrap_reps']} reps).",
        "",
        "| Model | AUC | Log loss | Accuracy | F1 | Brier | ECE |",
        "|---|---|---|---|---|---|---|",
    ]
    for n in order:
        p, c = point[n], ci[n]
        mark = " ⭐" if n == selection["chosen"] else ""
        lines.append(
            f"| {LABELS.get(n, n)}{mark} | {fmt_ci(p['auc'], c['auc'], 3)} | {fmt_ci(p['log_loss'], c['log_loss'], 3)} | "
            f"{fmt_ci(p['accuracy'], c['accuracy'], 3)} | {fmt_ci(p['f1'], c['f1'], 3)} | "
            f"{fmt_ci(p['brier'], c['brier'], 3)} | {fmt_ci(p['ece'], c['ece'], 3)} |"
        )
    lines += [
        "",
        f"### Improvement over the {LABELS[ref].lower()} (paired bootstrap)",
        "",
        "| Model | Δ AUC (95% CI) | Δ log loss (95% CI) |",
        "|---|---|---|",
    ]
    for n in order:
        if n == ref:
            continue
        da, dl = ci[n]["delta_auc"], ci[n]["delta_log_loss"]
        lines.append(
            f"| {LABELS.get(n, n)} | {point[n]['auc'] - point[ref]['auc']:+.4f} "
            f"({da[0]:+.4f} to {da[1]:+.4f}) | {point[n]['log_loss'] - point[ref]['log_loss']:+.4f} "
            f"({dl[0]:+.4f} to {dl[1]:+.4f}) |"
        )
    lines += [
        "",
        "An interval that excludes 0 means the difference is unlikely to be due to which students happened to be in the test set.",
        "",
        "![Calibration](reliability.png)",
        "",
        "## What the models learned",
        "",
        *interp,
        "## Test-set access log",
        "",
        "| # | Evaluated at | Selected model |",
        "|---|---|---|",
        *[f"| {i + 1} | {h['evaluated_at']} | {h['chosen']} |" for i, h in enumerate(history)],
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out / 'report.md'}")


if __name__ == "__main__":
    main()
