"""Export the trained FoundationalASSIST knowledge-tracing models for serving.

Input:  the notebook's checkpoints (ml/notebooks/kt_outputs/{dkt,dkt_q}.pt) and the raw
        FoundationalASSIST CSVs (never committed: CC BY-NC 4.0, gated download).
Output: backend/model_artifacts/foundationalassist/
        - dkt_q.npz, dkt.npz      weights as float32 NumPy arrays (no PyTorch needed to serve)
        - kt_meta.json            index maps, architecture, input convention, test metrics,
                                  and the NumPy-vs-PyTorch parity check result
        - question_stats.json     per-question difficulty from TRAINING students only

The skill/question index maps are rebuilt exactly as the notebook built them (same cleaning,
same seed-42 student split), and the parity check proves the exported weights reproduce the
PyTorch model's predictions. Requires torch (pip install torch) besides the ml package deps.

    python scripts/export_kt.py --data-dir "C:/Users/me/Downloads"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
CKPT_DIR = ROOT / "ml" / "notebooks" / "kt_outputs"
OUT_DIR = ROOT / "backend" / "model_artifacts" / "foundationalassist"
SEED = 42
MAX_SK = 3
DIM = 128


def load(data_dir: Path):
    raw = pd.read_csv(data_dir / "Interactions.csv", index_col=0)
    skills = pd.read_csv(data_dir / "Skills.csv").drop_duplicates(subset=["problem_id", "skill_id"])
    df = raw.drop_duplicates(subset="id").dropna(subset=["discrete_score"]).copy()
    df["end_time"] = pd.to_datetime(df["end_time"], utc=True, format="ISO8601", errors="coerce")
    df = df.dropna(subset=["end_time"])
    df["correct"] = df["discrete_score"].astype(np.int8)
    df = df.sort_values(["user_id", "end_time", "id"]).reset_index(drop=True)
    return df, skills


def build_maps(df: pd.DataFrame, skills: pd.DataFrame):
    student_ids = np.sort(df["user_id"].unique())
    train_students, temp = train_test_split(student_ids, test_size=0.30, random_state=SEED)
    val_students, _ = train_test_split(temp, test_size=0.50, random_state=SEED)
    split = pd.Series("test", index=student_ids)
    split[train_students] = "train"
    split[val_students] = "val"
    df["split"] = df["user_id"].map(split).values
    skill_ids = np.sort(skills["skill_id"].unique())
    train_q = np.sort(df.loc[df.split == "train", "problem_id"].unique())
    return df, [int(s) for s in skill_ids], [int(q) for q in train_q]


def question_stats(df: pd.DataFrame) -> dict:
    tr = df[df.split == "train"]
    g = tr.groupby("problem_id")["correct"].agg(["sum", "count"])
    glob = float(tr["correct"].mean())
    out = {}
    for pid, row in g.iterrows():
        n = int(row["count"])
        out[str(int(pid))] = {
            "attempts": n,
            "success_rate": round(float(row["sum"]) / n, 4),
            # shrunk toward the global rate so rarely-attempted questions aren't extreme
            "smoothed_rate": round((float(row["sum"]) + 5 * glob) / (n + 5), 4),
        }
    return {
        "global_success_rate": round(glob, 4),
        "source": "training students only",
        "questions": out,
    }


def export_weights(
    ckpt: Path, use_question: bool, n_skills: int, n_q: int
) -> dict[str, np.ndarray]:
    import torch

    state = torch.load(ckpt, map_location="cpu")
    assert state["num_skills"] == n_skills, (state["num_skills"], n_skills)
    assert state["num_q"] == n_q, (state["num_q"], n_q)
    sd = {k: v.numpy().astype(np.float32) for k, v in state["state_dict"].items()}
    expected = {
        "skill_resp.emb.weight",
        "skill_out.emb.weight",
        "inp.0.weight",
        "inp.0.bias",
        "inp.1.weight",
        "inp.1.bias",
        "enc.weight_ih_l0",
        "enc.weight_hh_l0",
        "enc.bias_ih_l0",
        "enc.bias_hh_l0",
        "head.0.weight",
        "head.0.bias",
        "head.3.weight",
        "head.3.bias",
    }
    if use_question:
        expected |= {"q_resp.weight", "q_out.weight", "q_bias.weight"}
    assert expected == set(sd), set(sd) ^ expected
    return {k.replace(".", "__"): v for k, v in sd.items()}


def torch_model(ckpt: Path, use_question: bool, n_skills: int, n_q: int):
    """Rebuild the notebook's KTModel (LSTM variant) exactly, for the parity check."""
    import torch
    import torch.nn as nn

    class SkillBag(nn.Module):
        def __init__(self, n, dim):
            super().__init__()
            self.emb = nn.Embedding(n, dim, padding_idx=0)

        def forward(self, idx):
            e = self.emb(idx)
            cnt = (idx > 0).sum(-1, keepdim=True).clamp(min=1)
            return e.sum(-2) / cnt

    class KT(nn.Module):
        def __init__(self):
            super().__init__()
            self.skill_resp = SkillBag(2 * n_skills, DIM)
            self.skill_out = SkillBag(n_skills, DIM)
            in_dim, head_in = DIM, 2 * DIM
            if use_question:
                self.q_resp = nn.Embedding(2 * n_q, DIM, padding_idx=0)
                self.q_out = nn.Embedding(n_q, DIM, padding_idx=0)
                self.q_bias = nn.Embedding(n_q, 1, padding_idx=0)
                in_dim, head_in = 2 * DIM + 3, 3 * DIM
            self.inp = nn.Sequential(nn.Linear(in_dim, DIM), nn.LayerNorm(DIM), nn.Dropout(0.2))
            self.enc = nn.LSTM(DIM, DIM, batch_first=True)
            self.head = nn.Sequential(
                nn.Linear(head_in, DIM), nn.ReLU(), nn.Dropout(0.2), nn.Linear(DIM, 1)
            )

        def forward(self, q_in, sk_in, r_in, f_in, q_out, sk_out):
            sr = torch.where(sk_in > 0, 2 * sk_in + r_in.unsqueeze(-1), torch.zeros_like(sk_in))
            parts = [self.skill_resp(sr)]
            if use_question:
                qr = torch.where(q_in > 0, 2 * q_in + r_in, torch.zeros_like(r_in))
                parts += [self.q_resp(qr), f_in]
            h, _ = self.enc(self.inp(torch.cat(parts, -1)))
            parts = [h, self.skill_out(sk_out)]
            if use_question:
                parts.append(self.q_out(q_out))
            logit = self.head(torch.cat(parts, -1)).squeeze(-1)
            if use_question:
                logit = logit + self.q_bias(q_out).squeeze(-1)
            return torch.sigmoid(logit)

    m = KT()
    m.load_state_dict(torch.load(ckpt, map_location="cpu")["state_dict"])
    return m.eval()


def parity(df, skills, skill_ids, train_q, use_question, ckpt, npz_path) -> float:
    """Max |p_numpy - p_torch| over every prediction for 20 validation students."""
    import torch

    sys.path.insert(0, str(ROOT / "backend"))
    from app.ml.dkt import KTInference  # the serving implementation under test

    model = KTInference.from_files(
        npz_path, use_question=use_question, skill_ids=skill_ids, question_ids=train_q
    )
    tm = torch_model(ckpt, use_question, len(skill_ids) + 1, len(train_q) + 1)
    skill_idx = {s: i + 1 for i, s in enumerate(skill_ids)}
    q_idx = {q: i + 1 for i, q in enumerate(train_q)}
    prob_skills = skills.groupby("problem_id")["skill_id"].apply(
        lambda s: [skill_idx[x] for x in s][:MAX_SK]
    )
    worst = 0.0
    for uid in df[df.split == "val"]["user_id"].unique()[:20]:
        d = df[df.user_id == uid]
        n = len(d)
        sk = np.zeros((n, MAX_SK), dtype=np.int64)
        for j, lst in enumerate(d["problem_id"].map(prob_skills)):
            sk[j, : len(lst)] = lst
        q = d["problem_id"].map(q_idx).fillna(0).astype(np.int64).to_numpy()
        r = d["correct"].to_numpy().astype(np.int64)
        secs = d["end_time"].astype("int64").to_numpy() / 1e9
        gap = np.r_[0.0, np.diff(secs)]
        f = np.stack(
            [
                np.log1p(d["hint_count"].clip(upper=10).to_numpy()),
                d["saw_answer"].astype(float).to_numpy(),
                np.log1p(np.maximum(gap, 0)) / 10.0,
            ],
            1,
        ).astype(np.float32)
        with torch.no_grad():
            pt = tm(
                *(
                    torch.as_tensor(a).unsqueeze(0)
                    for a in (q[:-1], sk[:-1], r[:-1], f[:-1], q[1:], sk[1:])
                )
            )[0].numpy()
        pn = model.predict_sequence(q[:-1], sk[:-1], r[:-1], f[:-1], q[1:], sk[1:])
        worst = max(worst, float(np.abs(pt - pn).max()))
    return worst


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, type=Path)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    df, skills = load(args.data_dir)
    df, skill_ids, train_q = build_maps(df, skills)
    print(f"rows {len(df):,} | skills {len(skill_ids)} | train questions {len(train_q)}")

    results = json.loads((CKPT_DIR / "results.json").read_text())
    meta = {
        "dataset": "FoundationalASSIST (ASSISTments; CC BY-NC 4.0; arXiv:2602.00070)",
        "label": "1 = correct on the first attempt with no hint and the answer not shown",
        "split": "by student 70/15/15, seed 42",
        "notebook": "ml/notebooks/02_foundationalassist_knowledge_tracing.ipynb",
        "skill_ids": skill_ids,  # index i+1 = skill_ids[i]; 0 = padding
        "question_ids": train_q,  # index i+1 = question_ids[i]; 0 = unknown question
        "max_skills_per_question": MAX_SK,
        "dim": DIM,
        "input_features": [
            "log1p(min(hint_count, 10)) of that attempt",
            "saw_answer (0/1) of that attempt",
            "log1p(seconds since the previous attempt) / 10 (0 for the first attempt)",
        ],
        "models": {},
    }
    for name, use_q in (("dkt_q", True), ("dkt", False)):
        ckpt = CKPT_DIR / f"{name}.pt"
        arrays = export_weights(ckpt, use_q, len(skill_ids) + 1, len(train_q) + 1)
        npz = OUT_DIR / f"{name}.npz"
        np.savez_compressed(npz, **arrays)
        diff = parity(df, skills, skill_ids, train_q, use_q, ckpt, npz)
        print(f"{name}: parity max |numpy - torch| = {diff:.2e}")
        assert diff < 1e-4, "exported weights do not reproduce the PyTorch model"
        label = {"dkt_q": "DKT-Q", "dkt": "DKT"}[name]
        meta["models"][name] = {
            "display_name": {"dkt_q": "DKT-Q (LSTM + question embeddings)", "dkt": "DKT (LSTM)"}[
                name
            ],
            "uses_question_ids": use_q,
            "file": npz.name,
            "sha256": sha256(npz),
            "parameters": int(sum(a.size for a in arrays.values())),
            "parity_max_abs_diff": diff,
            "test_metrics": results["test"].get(label),
            "validation_metrics": results["val"].get(label),
        }
    (OUT_DIR / "kt_meta.json").write_text(json.dumps(meta, indent=1))
    (OUT_DIR / "question_stats.json").write_text(json.dumps(question_stats(df)))
    print("wrote", OUT_DIR)


if __name__ == "__main__":
    main()
