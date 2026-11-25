"""Export the LSTM + Attention knowledge-tracing model (notebook 04) for serving.

Input:  ml/notebooks/lstm_outputs/ (the Kaggle run of 04_lstm_variants_kaggle.ipynb: the three
        dkt_q_lstm_attn_seed*.pt checkpoints and results_lstm.json) and the raw
        FoundationalASSIST CSVs (never committed: CC BY-NC 4.0, gated download).
Output: backend/model_artifacts/foundationalassist/
        - dkt_q_attn.npz          weights as float32 NumPy arrays
        - kt_meta.json            gains models["dkt_q_attn"] and "default_model": "dkt_q_attn";
                                  the existing dkt_q / dkt entries are kept unchanged

Which seed: the one with the lowest validation log loss (test numbers are never used to choose).
Checks, all of which must pass before anything is written:
- the notebook's skill and question index maps equal the ones already served (same split),
- NumPy predict_sequence() reproduces PyTorch for every attempt of 20 validation students,
- the serving path (state() + predict_questions(), as app/tutor/kt.py uses it) reproduces
  PyTorch's prediction for later attempts of those students.

    python ml/scripts/export_kt_attn.py --data-dir "C:/Users/me/Downloads"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from export_kt import MAX_SK, OUT_DIR, ROOT, build_maps, load, sha256

RUN_DIR = ROOT / "ml" / "notebooks" / "lstm_outputs"
NAME = "dkt_q_attn"
LABEL = "DKT-Q-LSTM+Attn"  # the model's name in results_lstm.json
DIM, HEADS = 128, 4
EXPECTED = {
    "skill_resp.emb.weight",
    "skill_out.emb.weight",
    "q_resp.weight",
    "q_out.weight",
    "q_bias.weight",
    "inp.0.weight",
    "inp.0.bias",
    "inp.1.weight",
    "inp.1.bias",
    "enc.weight_ih_l0",
    "enc.weight_hh_l0",
    "enc.bias_ih_l0",
    "enc.bias_hh_l0",
    "query.weight",
    "query.bias",
    "attn.in_proj_weight",
    "attn.in_proj_bias",
    "attn.out_proj.weight",
    "attn.out_proj.bias",
    "attn_norm.weight",
    "attn_norm.bias",
    "head.0.weight",
    "head.0.bias",
    "head.3.weight",
    "head.3.bias",
}


def torch_model(state_dict, n_skills: int, n_q: int):
    """The notebook's KTVariant(kind="lstm_attn"), rebuilt exactly (eval mode)."""
    import torch
    import torch.nn as nn

    class SkillBag(nn.Module):
        def __init__(self, n, dim):
            super().__init__()
            self.emb = nn.Embedding(n, dim, padding_idx=0)

        def forward(self, idx):
            return self.emb(idx).sum(-2) / (idx > 0).sum(-1, keepdim=True).clamp(min=1)

    class KT(nn.Module):
        def __init__(self):
            super().__init__()
            self.skill_resp = SkillBag(2 * n_skills, DIM)
            self.skill_out = SkillBag(n_skills, DIM)
            self.q_resp = nn.Embedding(2 * n_q, DIM, padding_idx=0)
            self.q_out = nn.Embedding(n_q, DIM, padding_idx=0)
            self.q_bias = nn.Embedding(n_q, 1, padding_idx=0)
            self.inp = nn.Sequential(
                nn.Linear(2 * DIM + 3, DIM), nn.LayerNorm(DIM), nn.Dropout(0.2)
            )
            self.enc = nn.LSTM(DIM, DIM, batch_first=True)
            self.query = nn.Linear(2 * DIM, DIM)
            self.attn = nn.MultiheadAttention(DIM, HEADS, dropout=0.2, batch_first=True)
            self.attn_norm = nn.LayerNorm(DIM)
            self.head = nn.Sequential(
                nn.Linear(4 * DIM, DIM), nn.ReLU(), nn.Dropout(0.2), nn.Linear(DIM, 1)
            )

        def forward(self, q_in, sk_in, r_in, f_in, q_out, sk_out):
            sr = torch.where(sk_in > 0, 2 * sk_in + r_in.unsqueeze(-1), torch.zeros_like(sk_in))
            qr = torch.where(q_in > 0, 2 * q_in + r_in, torch.zeros_like(r_in))
            x = self.inp(torch.cat([self.skill_resp(sr), self.q_resp(qr), f_in], -1))
            h, _ = self.enc(x)
            L = x.size(1)
            target = [self.skill_out(sk_out), self.q_out(q_out)]
            future = torch.triu(torch.ones(L, L, dtype=torch.bool), 1)
            ctx, _ = self.attn(
                self.query(torch.cat(target, -1)), h, h, attn_mask=future, need_weights=False
            )
            logit = self.head(torch.cat([h, *target, self.attn_norm(ctx)], -1)).squeeze(-1)
            return torch.sigmoid(logit + self.q_bias(q_out).squeeze(-1))

    m = KT()
    m.load_state_dict(state_dict)
    return m.eval()


def pick_seed() -> tuple[int, dict]:
    import torch

    best = None
    for path in sorted(RUN_DIR.glob("dkt_q_lstm_attn_seed*.pt")):
        ck = torch.load(path, map_location="cpu", weights_only=True)
        val = min(h["val_LogLoss"] for h in ck["history"])
        print(f"{path.name}: best validation log loss {val:.5f}")
        if best is None or val < best[0]:
            best = (val, ck)
    if best is None:
        raise SystemExit(f"no dkt_q_lstm_attn_seed*.pt in {RUN_DIR}")
    return int(best[1]["seed"]), best[1]


def parity(df, skills, skill_ids, train_q, tm, npz_path) -> tuple[float, float]:
    import torch

    sys.path.insert(0, str(ROOT / "backend"))
    from app.ml.dkt import Attempt, KTInference  # the serving implementation under test

    served = KTInference.from_files(
        npz_path, True, skill_ids, train_q, NAME, architecture="lstm_attn", heads=HEADS
    )
    skill_idx = {s: i + 1 for i, s in enumerate(skill_ids)}
    q_idx = {q: i + 1 for i, q in enumerate(train_q)}
    raw_skills = skills.groupby("problem_id")["skill_id"].apply(lambda s: list(s)[:MAX_SK])
    seq_worst = state_worst = 0.0
    for uid in df[df.split == "val"]["user_id"].unique()[:20]:
        d = df[df.user_id == uid]
        n = len(d)
        sk_raw = [raw_skills.get(p, []) for p in d["problem_id"]]
        sk = np.zeros((n, MAX_SK), dtype=np.int64)
        for j, lst in enumerate(sk_raw):
            sk[j, : len(lst)] = [skill_idx[x] for x in lst]
        q = d["problem_id"].map(q_idx).fillna(0).astype(np.int64).to_numpy()
        r = d["correct"].to_numpy().astype(np.int64)
        secs = d["end_time"].astype("int64").to_numpy() / 1e9
        gap = np.r_[0.0, np.diff(secs)]
        hints = d["hint_count"].fillna(0).to_numpy()
        saw = d["saw_answer"].astype(float).to_numpy()
        f = np.stack(
            [np.log1p(np.minimum(hints, 10)), saw, np.log1p(np.maximum(gap, 0)) / 10.0], 1
        ).astype(np.float32)
        args = (q[:-1], sk[:-1], r[:-1], f[:-1], q[1:], sk[1:])
        with torch.no_grad():
            pt = tm(*(torch.as_tensor(a).unsqueeze(0) for a in args))[0].numpy()
        pn = served.predict_sequence(*args)
        seq_worst = max(seq_worst, float(np.abs(pt - pn).max()))
        # serving path: history of the first k attempts, then score attempt k
        attempts = [
            Attempt(int(p), [int(x) for x in s], bool(c), int(hh), bool(sa), float(g))
            for p, s, c, hh, sa, g in zip(d["problem_id"], sk_raw, r, hints, saw, gap, strict=True)
        ]
        for k in (1, n // 2, n - 1):
            h = served.state(attempts[:k])
            p_next = served.predict_questions(h, [(attempts[k].question_id, attempts[k].skill_ids)])
            state_worst = max(state_worst, abs(float(p_next[0]) - float(pt[k - 1])))
    return seq_worst, state_worst


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, type=Path)
    args = ap.parse_args()

    meta_path = OUT_DIR / "kt_meta.json"
    meta = json.loads(meta_path.read_text())
    df, skills = load(args.data_dir)
    df, skill_ids, train_q = build_maps(df, skills)
    assert skill_ids == meta["skill_ids"], "skill index differs from the served models"
    assert train_q == meta["question_ids"], "question index differs from the served models"

    seed, ck = pick_seed()
    print(f"chosen: seed {seed} (lowest validation log loss)")
    assert (ck["num_skills"], ck["num_q"]) == (len(skill_ids) + 1, len(train_q) + 1)
    assert ck["kind"] == "lstm_attn" and ck["dim"] == DIM
    sd = {k: v.numpy().astype(np.float32) for k, v in ck["state_dict"].items()}
    assert set(sd) == EXPECTED, set(sd) ^ EXPECTED

    npz = OUT_DIR / f"{NAME}.npz"
    np.savez_compressed(npz, **{k.replace(".", "__"): v for k, v in sd.items()})
    tm = torch_model(ck["state_dict"], len(skill_ids) + 1, len(train_q) + 1)
    seq_diff, state_diff = parity(df, skills, skill_ids, train_q, tm, npz)
    print(f"parity max |numpy - torch|: sequence {seq_diff:.2e}, serving path {state_diff:.2e}")
    if max(seq_diff, state_diff) >= 1e-4:
        npz.unlink()
        raise SystemExit("exported weights do not reproduce the PyTorch model; nothing written")

    results = json.loads((RUN_DIR / "results_lstm.json").read_text())
    hist = ck["history"]
    best_epoch = min(hist, key=lambda h: h["val_LogLoss"])
    meta["models"][NAME] = {
        "display_name": "DKT-Q + Attention (LSTM + attention over earlier attempts)",
        "architecture": "lstm_attn",
        "heads": HEADS,
        "uses_question_ids": True,
        "file": npz.name,
        "sha256": sha256(npz),
        "parameters": int(sum(a.size for a in sd.values())),
        "parity_max_abs_diff": max(seq_diff, state_diff),
        "parity_detail": {"sequence": seq_diff, "serving_path": state_diff},
        "notebook": "ml/notebooks/04_lstm_variants_kaggle.ipynb",
        "training_seed": seed,
        "chosen_by": "lowest validation log loss of 3 training seeds",
        "test_metrics": results["test_per_seed"][f"{LABEL} | seed {seed}"],
        "validation_metrics": {k[4:]: v for k, v in best_epoch.items() if k.startswith("val_")},
        "comparison_with_dkt_q": {
            "same_run_baseline": "DKT-Q (LSTM), same split and settings, 3 seeds",
            "test_auc_mean_3_seeds": {
                "DKT-Q": results["test_mean_over_seeds"]["DKT-Q (LSTM)"]["AUC"],
                "DKT-Q + Attention": results["test_mean_over_seeds"][LABEL]["AUC"],
            },
            "paired_auc_difference_seed42": results["paired_vs_baseline"][LABEL],
        },
    }
    meta["default_model"] = NAME
    meta_path.write_text(json.dumps(meta, indent=1))
    print("wrote", npz.name, "and", meta_path.name, "| default_model =", NAME)


if __name__ == "__main__":
    main()
