"""Train, evaluate and export the Geography DKT-Q (Slepemapy.cz 2015-05-21, ODbL 1.0).

Data (never committed): answer.csv, place.csv, place_type.csv from
http://www.fi.muni.cz/adaptivelearning/data/slepemapy/2015-05-21.zip
Citation: Papousek, Pelanek & Stanislav (2016), Adaptive Geography Practice Data Set,
Journal of Learning Analytics 3(2), 317-321.

What it does (config: ml/configs/geography.yaml):
1. Keeps answers on the six shipped maps whose asked place is askable (it has geometry in
   backend/app/tutor/seeddata/geography/geometry_<map>.json, which already leaves out disputed
   places) and whose skill (map x place type) has enough places and answers.
2. Question id = MENTORX item id: 100_000_000 + place_id * 100 + map_idx * 2 + dir
   (dir 0 = "name the highlighted place" = dataset type 2, dir 1 = "find it" = type 1).
   Skill id = 1_000_000 + map_idx * 100 + place_type_id. Label = answered place == asked place
   ("I don't know" counts as wrong). Hints and saw_answer are 0; the time gap comes from
   `inserted`. This is exactly the Mathematics input convention, so the backend serves it with
   the same NumPy code (backend/app/ml/dkt.py).
3. Samples at most `max_users` students (seed 42), keeps each one's first `max_answers_per_user`
   answers, splits by student 70/15/15 (seed 42), trains the notebook's LSTM DKT-Q on CPU with
   early stopping on validation log loss, and evaluates on the held-out test students against
   a per-question baseline (training students' success rate of that question).
4. Exports backend/model_artifacts/geography/{dkt_q.npz, kt_meta.json, question_stats.json,
   NOTICE.txt} and checks that the NumPy forward pass reproduces PyTorch (max abs diff <= 1e-5).

    python ml/scripts/train_geography_kt.py --data-dir <slepemapy folder>   (needs torch)
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import yaml
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "ml" / "configs" / "geography.yaml"
GEOMETRY_DIR = ROOT / "backend" / "app" / "tutor" / "seeddata" / "geography"
OUT_DIR = ROOT / "backend" / "model_artifacts" / "geography"
WORK_DIR = ROOT / "ml" / "artifacts" / "geography"  # checkpoints and logs (gitignored)
MAX_SK = 3

MAP_IDX = {"europe": 1, "africa": 2, "samerica": 3, "namerica": 4, "oceania": 5, "us": 6}
MAP_SHORT = {
    "europe": "EU",
    "africa": "AF",
    "samerica": "SA",
    "namerica": "NA",
    "oceania": "OC",
    "us": "US",
}
MAP_NAME = {
    "europe": "Europe",
    "africa": "Africa",
    "samerica": "South America",
    "namerica": "North America",
    "oceania": "Oceania",
    "us": "United States",
}
TYPE_CODE = {
    1: "COUNTRY",
    2: "CITY",
    5: "RIVER",
    6: "LAKE",
    7: "STATE",
    8: "MOUNTAINS",
    9: "ISLAND",
}
TYPE_PLURAL = {
    1: "Countries",
    2: "Cities",
    5: "Rivers",
    6: "Lakes",
    7: "States",
    8: "Mountains",
    9: "Islands",
}
NEVER_ASKED = {"xk", "eh", "xs", "fk", "ps", "tw", "pristina", "bir_lehlou", "laayoune", "hargeysa"}


def item_id(place_id: int, map_code: str, direction: int) -> int:
    return 100_000_000 + int(place_id) * 100 + MAP_IDX[map_code] * 2 + int(direction)


def skill_id(map_code: str, type_id: int) -> int:
    return 1_000_000 + MAP_IDX[map_code] * 100 + int(type_id)


def skill_name(map_code: str, type_id: int) -> str:
    if map_code == "us":
        return "US states" if type_id == 7 else "Cities of the United States"
    return f"{TYPE_PLURAL[type_id]} of {MAP_NAME[map_code]}"


def set_seed(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)


# ------------------------------------------------------------------ data


def load(data_dir: Path, cfg: dict):
    places = pd.read_csv(data_dir / "place.csv", sep=";")
    code_of = dict(zip(places["id"], places["code"].str.lower(), strict=True))
    type_of = dict(zip(places["id"], places["type"], strict=True))
    map_place = {int(places.loc[places["code"] == m, "id"].iloc[0]): m for m in cfg["maps"]}
    parts = []
    for ch in pd.read_csv(
        data_dir / "answer.csv",
        sep=";",
        chunksize=2_000_000,
        usecols=["id", "user", "place_asked", "place_answered", "type", "inserted", "place_map"],
        dtype={"place_answered": "float64", "place_map": "float64"},
    ):
        parts.append(ch[ch["place_map"].isin(list(map_place))])
    df = pd.concat(parts, ignore_index=True)
    df["map"] = df["place_map"].astype(int).map(map_place)
    df["inserted"] = pd.to_datetime(df["inserted"], format="%Y-%m-%d %H:%M:%S")
    geometry = {
        m: json.loads((GEOMETRY_DIR / f"geometry_{m}.json").read_text(encoding="utf-8"))
        for m in cfg["maps"]
    }
    return df, places, code_of, type_of, geometry


def catalog(df, code_of, type_of, geometry, cfg):
    """Skills (map x place type) that pass the shipping thresholds, with their places."""
    askable = df["place_asked"].map(code_of)
    ok = np.array(
        [c in geometry[m] and c not in NEVER_ASKED for c, m in zip(askable, df["map"], strict=True)]
    )
    d = df[ok].copy()
    d["ptype"] = d["place_asked"].map(type_of).astype(int)
    skills = []
    for (m, t), g in d.groupby(["map", "ptype"]):
        if t not in TYPE_CODE:
            continue
        pl = sorted(int(p) for p in g["place_asked"].unique())
        if len(pl) >= cfg["min_places_per_skill"] and len(g) >= cfg["min_answers_per_skill"]:
            skills.append(
                {
                    "id": skill_id(m, t),
                    "code": f"GEO.{MAP_SHORT[m]}.{TYPE_CODE[t]}",
                    "name": skill_name(m, t),
                    "map": m,
                    "map_idx": MAP_IDX[m],
                    "domain_code": MAP_SHORT[m],
                    "domain_name": MAP_NAME[m],
                    "place_type_id": int(t),
                    "places": pl,
                    "dataset_answers": int(len(g)),
                }
            )
    skills.sort(key=lambda s: s["id"])
    keep = {(s["map"], s["place_type_id"]) for s in skills}
    d = d[[(m, t) in keep for m, t in zip(d["map"], d["ptype"], strict=True)]].copy()
    d["skill"] = [skill_id(m, t) for m, t in zip(d["map"], d["ptype"], strict=True)]
    d["dir"] = (d["type"] == 1).astype(int)  # type 1 = find on map = locate_place
    d["item"] = [
        item_id(p, m, k) for p, m, k in zip(d["place_asked"], d["map"], d["dir"], strict=True)
    ]
    d["correct"] = (d["place_answered"] == d["place_asked"]).astype(np.int8)
    return d, skills


def confusions(d: pd.DataFrame, skills: list[dict]) -> dict[int, list[int]]:
    """Per item: same-skill places most often given instead of the right one (all students)."""
    same = {(s["map"], p): s["id"] for s in skills for p in s["places"]}
    wrong = d[(d["correct"] == 0) & d["place_answered"].notna()].copy()
    wrong["ans"] = wrong["place_answered"].astype(int)
    wrong = wrong[
        [
            same.get((m, a)) == s
            for m, a, s in zip(wrong["map"], wrong["ans"], wrong["skill"], strict=True)
        ]
    ]
    out: dict[int, list[int]] = {}
    for it, g in wrong.groupby("item"):
        out[int(it)] = [int(p) for p in g["ans"].value_counts().index[:10]]
    return out


# ------------------------------------------------------------------ model (notebook's KTModel, LSTM)


class SkillBag(nn.Module):
    def __init__(self, n, dim):
        super().__init__()
        self.emb = nn.Embedding(n, dim, padding_idx=0)

    def forward(self, idx):
        e = self.emb(idx)
        cnt = (idx > 0).sum(-1, keepdim=True).clamp(min=1)
        return e.sum(-2) / cnt


class KTModel(nn.Module):
    def __init__(self, num_skills: int, num_q: int, dim: int, dropout: float):
        super().__init__()
        self.skill_resp = SkillBag(2 * num_skills, dim)
        self.skill_out = SkillBag(num_skills, dim)
        self.q_resp = nn.Embedding(2 * num_q, dim, padding_idx=0)
        self.q_out = nn.Embedding(num_q, dim, padding_idx=0)
        self.q_bias = nn.Embedding(num_q, 1, padding_idx=0)
        nn.init.zeros_(self.q_bias.weight)
        self.inp = nn.Sequential(
            nn.Linear(2 * dim + 3, dim), nn.LayerNorm(dim), nn.Dropout(dropout)
        )
        self.enc = nn.LSTM(dim, dim, batch_first=True, num_layers=1)
        self.head = nn.Sequential(
            nn.Linear(3 * dim, dim), nn.ReLU(), nn.Dropout(dropout), nn.Linear(dim, 1)
        )

    def forward(self, b):
        sk_in, r_in = b["sk_in"], b["r_in"]
        sr = torch.where(sk_in > 0, 2 * sk_in + r_in.unsqueeze(-1), torch.zeros_like(sk_in))
        qr = torch.where(b["q_in"] > 0, 2 * b["q_in"] + r_in, torch.zeros_like(r_in))
        x = self.inp(torch.cat([self.skill_resp(sr), self.q_resp(qr), b["f_in"]], -1))
        L = x.size(1)
        packed = nn.utils.rnn.pack_padded_sequence(
            x, b["lengths"].cpu(), batch_first=True, enforce_sorted=False
        )
        h, _ = self.enc(packed)
        h, _ = nn.utils.rnn.pad_packed_sequence(h, batch_first=True, total_length=L)
        z = torch.cat([h, self.skill_out(b["sk_out"]), self.q_out(b["q_out"])], -1)
        return self.head(z).squeeze(-1) + self.q_bias(b["q_out"]).squeeze(-1)


def collate(batch):
    L = max(len(x["r"]) for x in batch) - 1
    B = len(batch)
    out = {
        "q_in": torch.zeros(B, L, dtype=torch.long),
        "sk_in": torch.zeros(B, L, MAX_SK, dtype=torch.long),
        "r_in": torch.zeros(B, L, dtype=torch.long),
        "f_in": torch.zeros(B, L, 3),
        "q_out": torch.zeros(B, L, dtype=torch.long),
        "sk_out": torch.zeros(B, L, MAX_SK, dtype=torch.long),
        "y": torch.zeros(B, L),
        "mask": torch.zeros(B, L, dtype=torch.bool),
        "lengths": torch.zeros(B, dtype=torch.long),
    }
    for i, x in enumerate(batch):
        n = len(x["r"]) - 1
        out["q_in"][i, :n] = torch.as_tensor(x["q"][:-1])
        out["sk_in"][i, :n] = torch.as_tensor(x["sk"][:-1])
        out["r_in"][i, :n] = torch.as_tensor(x["r"][:-1])
        out["f_in"][i, :n] = torch.as_tensor(x["f"][:-1])
        out["q_out"][i, :n] = torch.as_tensor(x["q"][1:])
        out["sk_out"][i, :n] = torch.as_tensor(x["sk"][1:])
        out["y"][i, :n] = torch.from_numpy(x["r"][1:].astype(np.float32))
        out["mask"][i, :n] = True
        out["lengths"][i] = n
    return out


def batches(seqs, size, rng=None):
    """Length-bucketed batches (similar lengths together = less padding); shuffled if rng."""
    order = sorted(range(len(seqs)), key=lambda i: len(seqs[i]["r"]))
    groups = [order[i : i + size] for i in range(0, len(order), size)]
    if rng is not None:
        rng.shuffle(groups)
    return groups


# ------------------------------------------------------------------ metrics


def ece_score(y, p, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    return float(
        sum(
            (idx == b).mean() * abs(y[idx == b].mean() - p[idx == b].mean())
            for b in range(bins)
            if (idx == b).any()
        )
    )


def metrics(y, p) -> dict:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {
        "AUC": round(float(roc_auc_score(y, p)), 5),
        "LogLoss": round(float(log_loss(y, p)), 5),
        "Accuracy": round(float(accuracy_score(y, p >= 0.5)), 5),
        "Brier": round(float(brier_score_loss(y, p)), 5),
        "ECE": round(ece_score(y, p), 5),
    }


def bootstrap_auc_ci(y, p, groups, reps, seed):
    rng = np.random.default_rng(seed)
    uniq, inv = np.unique(groups, return_inverse=True)
    rows_of = [np.flatnonzero(inv == g) for g in range(len(uniq))]
    aucs = []
    for _ in range(reps):
        rows = np.concatenate([rows_of[g] for g in rng.integers(0, len(uniq), len(uniq))])
        aucs.append(roc_auc_score(y[rows], p[rows]))
    lo, hi = np.percentile(aucs, [2.5, 97.5])
    return f"{lo:.3f}-{hi:.3f}"


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--smoke", action="store_true", help="tiny test run: baseline gate only warns")
    args = ap.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    seed = cfg["seed"]
    set_seed(seed)
    if args.threads:
        torch.set_num_threads(args.threads)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = WORK_DIR / "train_log.txt"
    log_path.write_text("", encoding="utf-8")

    def log(msg: str) -> None:
        print(msg, flush=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")

    t0 = time.time()
    raw, places, code_of, type_of, geometry = load(args.data_dir, cfg)
    log(f"answers on the shipped maps: {len(raw):,} ({time.time() - t0:.0f}s)")
    d, skills = catalog(raw, code_of, type_of, geometry, cfg)
    assert not set(d["place_asked"].map(code_of)) & NEVER_ASKED
    log(f"askable answers: {len(d):,} | skills {len(skills)} | items {d['item'].nunique()}")
    for s in skills:
        log(
            f"  {s['id']} {s['code']:18s} {s['name']:30s} places {len(s['places']):3d} answers {s['dataset_answers']:,}"
        )
    conf = confusions(d, skills)

    # ---- sample students, cap history, split by student
    d = d.sort_values(["user", "inserted", "id"]).reset_index(drop=True)
    counts = d.groupby("user").size()
    eligible = np.sort(counts.index[counts >= 2].to_numpy())
    rng = np.random.default_rng(seed)
    n_users = min(cfg["max_users"], len(eligible))
    sample = np.sort(rng.choice(eligible, n_users, replace=False))
    d = d[d["user"].isin(sample)]
    d = d[d.groupby("user").cumcount() < cfg["max_answers_per_user"]].reset_index(drop=True)
    tr_frac, va_frac, _ = cfg["split"]
    train_u, temp = train_test_split(sample, test_size=1 - tr_frac, random_state=seed)
    val_u, test_u = train_test_split(temp, test_size=0.5, random_state=seed)
    split = pd.Series("test", index=sample)
    split[train_u] = "train"
    split[val_u] = "val"
    d["split"] = d["user"].map(split).to_numpy()
    log(
        f"sample: {n_users:,} of {len(eligible):,} eligible students | rows {len(d):,} | "
        f"train/val/test students {len(train_u)}/{len(val_u)}/{len(test_u)}"
    )

    skill_ids = [s["id"] for s in skills]
    train_q = sorted(int(q) for q in d.loc[d.split == "train", "item"].unique())
    sk_idx = {s: i + 1 for i, s in enumerate(skill_ids)}
    q_idx = {q: i + 1 for i, q in enumerate(train_q)}
    num_skills, num_q = len(skill_ids) + 1, len(train_q) + 1

    users = d["user"].to_numpy()
    new_user = np.r_[True, users[1:] != users[:-1]]
    secs = d["inserted"].astype("int64").to_numpy() / 1e9
    gap = np.r_[0.0, np.diff(secs)]
    gap[new_user] = 0.0
    F = np.zeros((len(d), 3), dtype=np.float32)
    F[:, 2] = np.log1p(np.maximum(gap, 0)) / 10.0
    Q = d["item"].map(q_idx).fillna(0).astype(np.int64).to_numpy()
    SK = np.zeros((len(d), MAX_SK), dtype=np.int64)
    SK[:, 0] = d["skill"].map(sk_idx).to_numpy()
    R = d["correct"].astype(np.int64).to_numpy()
    starts = np.flatnonzero(new_user)
    ends = np.r_[starts[1:], len(d)]
    SPL = d["split"].to_numpy()
    seqs = {"train": [], "val": [], "test": []}
    for a, b in zip(starts, ends, strict=True):
        seqs[SPL[a]].append(
            {"rows": np.arange(a, b), "q": Q[a:b], "sk": SK[a:b], "r": R[a:b], "f": F[a:b]}
        )

    @torch.no_grad()
    def predict(model, part: str) -> np.ndarray:
        model.eval()
        probs = np.full(len(d), np.nan)
        for g in batches(seqs[part], 256):
            batch = [seqs[part][i] for i in g]
            p = torch.sigmoid(model(collate(batch))).numpy()
            for i, x in enumerate(batch):
                probs[x["rows"][1:]] = p[i, : len(x["r"]) - 1]
        return probs

    # ---- train
    set_seed(seed)
    model = KTModel(num_skills, num_q, cfg["dim"], cfg["dropout"])
    n_params = sum(p.numel() for p in model.parameters())
    log(
        f"DKT-Q: {n_params:,} parameters | torch {torch.__version__} | threads {torch.get_num_threads()}"
    )
    opt = torch.optim.AdamW(model.parameters(), lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=1)
    bce = nn.BCEWithLogitsLoss(reduction="sum")
    vr = np.flatnonzero(SPL == "val")
    y_all = R.astype(np.float64)
    best, best_state, bad, history = math.inf, None, 0, []
    brng = np.random.default_rng(seed)
    for epoch in range(1, cfg["max_epochs"] + 1):
        model.train()
        te, tot, cnt = time.time(), 0.0, 0
        for g in batches(seqs["train"], cfg["batch_size"], brng):
            b = collate([seqs["train"][i] for i in g])
            logits = model(b)
            m = b["mask"]
            loss = bce(logits[m], b["y"][m]) / m.sum()
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot += loss.item() * m.sum().item()
            cnt += m.sum().item()
        p = predict(model, "val")[vr]
        keep = ~np.isnan(p)
        vm = metrics(y_all[vr][keep], p[keep])
        sched.step(vm["LogLoss"])
        history.append(
            {
                "epoch": epoch,
                "train_loss": round(tot / cnt, 5),
                **{f"val_{k}": v for k, v in vm.items()},
            }
        )
        log(
            f"epoch {epoch:2d} | train {tot / cnt:.4f} | val logloss {vm['LogLoss']:.4f} AUC {vm['AUC']:.4f} "
            f"acc {vm['Accuracy']:.4f} | lr {opt.param_groups[0]['lr']:.0e} | {time.time() - te:.0f}s"
        )
        if vm["LogLoss"] < best - 1e-4:
            best, best_state, bad = vm["LogLoss"], copy.deepcopy(model.state_dict()), 0
        else:
            bad += 1
            if bad >= cfg["patience"]:
                log("early stop")
                break
    model.load_state_dict(best_state)
    ckpt = WORK_DIR / "dkt_q.pt"
    torch.save({"state_dict": best_state, "num_skills": num_skills, "num_q": num_q}, ckpt)

    # ---- evaluate on held-out test students, against the per-question baseline
    def evaluate(part: str) -> tuple[dict, dict, int]:
        rows = np.flatnonzero(SPL == part)
        p = predict(model, part)[rows]
        keep = ~np.isnan(p)  # the first answer of each student has no prediction
        rows, p = rows[keep], p[keep]
        y = y_all[rows]
        tr = d[d.split == "train"]
        rate = tr.groupby("item")["correct"].mean()
        glob = float(tr["correct"].mean())
        pb = d["item"].iloc[rows].map(rate).fillna(glob).to_numpy()
        users_r = users[rows]
        dm = metrics(y, p)
        bm = metrics(y, pb)
        if part == "test":
            dm["AUC 95% CI"] = bootstrap_auc_ci(y, p, users_r, cfg["bootstrap_reps"], seed)
            bm["AUC 95% CI"] = bootstrap_auc_ci(y, pb, users_r, cfg["bootstrap_reps"], seed)
        return dm, bm, len(rows)

    val_m, val_b, _ = evaluate("val")
    test_m, test_b, n_test = evaluate("test")
    log(f"TEST ({n_test:,} predictions) DKT-Q {test_m}")
    log(f"TEST baseline (per-question training success rate) {test_b}")
    if test_m["AUC"] <= test_b["AUC"]:
        assert args.smoke, "DKT-Q does not beat the per-question baseline"
        log("WARNING (smoke run): DKT-Q does not beat the baseline")

    # ---- export weights + NumPy parity
    sd = {k: v.numpy().astype(np.float32) for k, v in best_state.items()}
    npz = OUT_DIR / "dkt_q.npz"
    np.savez_compressed(npz, **{k.replace(".", "__"): v for k, v in sd.items()})
    sys.path.insert(0, str(ROOT / "backend"))
    from app.ml.dkt import KTInference  # the serving implementation under test

    served = KTInference.from_files(
        npz, use_question=True, skill_ids=skill_ids, question_ids=train_q
    )
    model.eval()
    worst = 0.0
    for x in seqs["val"][:20] + seqs["test"][:20]:
        if len(x["r"]) < 2:
            continue
        with torch.no_grad():
            pt = torch.sigmoid(model(collate([x])))[0].numpy()
        pn = served.predict_sequence(
            x["q"][:-1], x["sk"][:-1], x["r"][:-1], x["f"][:-1], x["q"][1:], x["sk"][1:]
        )
        worst = max(worst, float(np.abs(pt - pn).max()))
    # the stateful serving path too (state() + predict_questions(), as kt.py uses it)
    inv_q = {i: q for q, i in q_idx.items()}
    for x in seqs["test"][:5]:
        n = len(x["r"])
        if n < 2:
            continue
        with torch.no_grad():
            pt = torch.sigmoid(model(collate([x])))[0].numpy()[-1]
        from app.ml.dkt import Attempt

        hist = [
            Attempt(
                inv_q.get(int(x["q"][j]), -1),
                [skill_ids[int(x["sk"][j, 0]) - 1]],
                bool(x["r"][j]),
                0,
                False,
                float(math.expm1(x["f"][j, 2] * 10)),
            )
            for j in range(n - 1)
        ]
        h = served.state(hist)
        last_q = inv_q.get(int(x["q"][-1]), -1)
        pn = served.predict_questions(h, [(last_q, [skill_ids[int(x["sk"][-1, 0]) - 1]])])[0]
        worst = max(worst, abs(float(pt) - float(pn)))
    log(f"parity max |numpy - torch| = {worst:.2e}")
    assert worst <= 1e-5, "exported weights do not reproduce the PyTorch model"

    # ---- question stats (training students) + confusions (all students on the shipped maps)
    tr = d[d.split == "train"]
    g = tr.groupby("item")["correct"].agg(["sum", "count"])
    glob = float(tr["correct"].mean())
    all_items = sorted(item_id(p, s["map"], k) for s in skills for p in s["places"] for k in (0, 1))
    qstats = {}
    for it in all_items:
        n = int(g.loc[it, "count"]) if it in g.index else 0
        s_ = float(g.loc[it, "sum"]) if n else 0.0
        qstats[str(it)] = {
            "attempts": n,
            "success_rate": round(s_ / n, 4) if n else None,
            "smoothed_rate": round((s_ + 5 * glob) / (n + 5), 4),
            "confusions": conf.get(it, []),
        }
    (OUT_DIR / "question_stats.json").write_text(
        json.dumps(
            {
                "global_success_rate": round(glob, 4),
                "source": "success rates: training students only; confusions: every answer on the "
                "shipped maps (same-skill places most often answered instead, most frequent first)",
                "questions": qstats,
            }
        ),
        encoding="utf-8",
        newline="\n",
    )

    meta = {
        "dataset": "Slepemapy.cz 2015-05-21 (Adaptive Learning group, Masaryk University; "
        "Open Database License 1.0, contents DbCL 1.0)",
        "citation": "Papousek, J., Pelanek, R., & Stanislav, V. (2016). Adaptive Geography Practice "
        "Data Set. Journal of Learning Analytics, 3(2), 317-321. https://doi.org/10.18608/jla.2016.32.17",
        "label": "1 = the answered place is the asked place ('I don't know' counts as wrong)",
        "split": f"by student 70/15/15, seed {seed}",
        "sample": (
            f"{n_users:,} of {len(eligible):,} students with >= 2 askable answers (seeded random "
            f"sample, CPU budget); each student's first {cfg['max_answers_per_user']} answers"
        ),
        "script": "ml/scripts/train_geography_kt.py (config ml/configs/geography.yaml)",
        "trained_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "maps": cfg["maps"],
        "never_asked": sorted(NEVER_ASKED),
        "skills": skills,
        "skill_ids": skill_ids,
        "question_ids": train_q,
        "max_skills_per_question": MAX_SK,
        "dim": cfg["dim"],
        "input_features": [
            "log1p(min(hint_count, 10)) of that attempt (always 0 in the dataset)",
            "saw_answer (0/1) of that attempt (always 0 in the dataset)",
            "log1p(seconds since the previous attempt) / 10 (0 for the first attempt)",
        ],
        "rows": {
            "train": int((SPL == "train").sum()),
            "val": int((SPL == "val").sum()),
            "test": int((SPL == "test").sum()),
        },
        "test_predictions": n_test,
        "caveat": (
            "The source app mixed open map clicks with 2-6 option questions and its users were "
            "mostly Czech and Slovak students (2013-2015). MENTORX serves 4-option questions, so "
            "predictions are only approximately calibrated; observed answers always decide a "
            "student's skill status."
        ),
        "models": {
            "dkt_q": {
                "display_name": "DKT-Q (LSTM + question embeddings)",
                "uses_question_ids": True,
                "file": npz.name,
                "sha256": hashlib.sha256(npz.read_bytes()).hexdigest(),
                "parameters": int(n_params),
                "parity_max_abs_diff": worst,
                "test_metrics": test_m,
                "validation_metrics": val_m,
                "epochs": history,
            }
        },
        "baseline": {
            "name": "per-question success rate of training students (global rate if unseen)",
            "test_metrics": test_b,
            "validation_metrics": val_b,
        },
    }
    (OUT_DIR / "kt_meta.json").write_text(
        json.dumps(meta, indent=1), encoding="utf-8", newline="\n"
    )
    log(f"wrote {OUT_DIR} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
