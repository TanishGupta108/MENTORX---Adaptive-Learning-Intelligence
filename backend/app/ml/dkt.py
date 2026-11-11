"""Knowledge-tracing inference (DKT-Q / DKT) in plain NumPy.

The models were trained in PyTorch (ml/notebooks/02_foundationalassist_knowledge_tracing.ipynb).
`ml/scripts/export_kt.py` saves their weights as .npz and checks that THIS file reproduces the
PyTorch predictions (max difference recorded in kt_meta.json). Serving without PyTorch keeps
the API small enough for a 512 MB host and avoids a 200 MB dependency.

Input convention (must match training exactly):
- skills: index i+1 = meta.skill_ids[i]; 0 = padding. Up to 3 skills per question.
- questions: index i+1 = meta.question_ids[i] (questions seen by TRAINING students);
  0 = unknown question (the model then relies on its skills only).
- label r = 1 only for a first-attempt correct answer with no hint and the answer not shown.
- per-attempt features: [log1p(min(hints,10)), saw_answer, log1p(seconds since previous)/10].
- position t reads attempts 0..t and predicts attempt t+1.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

MAX_SK = 3


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


@dataclass
class Attempt:
    """One past answer, in the model's terms."""

    question_id: int  # original problem_id
    skill_ids: list[int]  # original skill ids (1-3)
    correct: bool  # already the training label (no hint, no answer shown)
    hints: int = 0
    saw_answer: bool = False
    seconds_since_previous: float = 0.0


@dataclass
class KTInference:
    w: dict[str, np.ndarray]
    use_question: bool
    skill_index: dict[int, int]
    question_index: dict[int, int]
    name: str = "dkt_q"
    meta: dict = field(default_factory=dict)

    # ------------------------------------------------------------ loading

    @classmethod
    def from_files(
        cls,
        npz_path: Path | str,
        use_question: bool,
        skill_ids: list[int],
        question_ids: list[int],
        name: str = "dkt_q",
        meta: dict | None = None,
    ) -> KTInference:
        with np.load(npz_path) as data:
            w = {k.replace("__", "."): data[k].astype(np.float32) for k in data.files}
        return cls(
            w=w,
            use_question=use_question,
            skill_index={int(s): i + 1 for i, s in enumerate(skill_ids)},
            question_index={int(q): i + 1 for i, q in enumerate(question_ids)},
            name=name,
            meta=meta or {},
        )

    @classmethod
    def from_artifacts(cls, artifact_dir: Path | str, name: str = "dkt_q") -> KTInference:
        d = Path(artifact_dir)
        meta = json.loads((d / "kt_meta.json").read_text())
        m = meta["models"][name]
        return cls.from_files(
            d / m["file"], m["uses_question_ids"], meta["skill_ids"], meta["question_ids"], name, m
        )

    # ------------------------------------------------------------ encoding helpers

    def skill_row(self, skill_ids: list[int]) -> np.ndarray:
        row = np.zeros(MAX_SK, dtype=np.int64)
        idx = [self.skill_index[s] for s in skill_ids if s in self.skill_index][:MAX_SK]
        row[: len(idx)] = idx
        return row

    def q_index(self, question_id: int) -> int:
        return self.question_index.get(int(question_id), 0)

    def supports_skill(self, skill_id: int) -> bool:
        return int(skill_id) in self.skill_index

    def supports_question(self, question_id: int) -> bool:
        return int(question_id) in self.question_index

    def _bag(self, table: str, idx: np.ndarray) -> np.ndarray:
        """Mean of the embeddings of non-zero indices; idx shape (..., 3)."""
        e = self.w[table][idx]  # (..., 3, D)
        cnt = np.maximum((idx > 0).sum(-1, keepdims=True), 1)
        return e.sum(-2) / cnt

    def _inputs(self, q, sk, r, f) -> np.ndarray:
        sr = np.where(sk > 0, 2 * sk + r[:, None], 0)
        parts = [self._bag("skill_resp.emb.weight", sr)]
        if self.use_question:
            qr = np.where(q > 0, 2 * q + r, 0)
            parts += [self.w["q_resp.weight"][qr], f.astype(np.float32)]
        x = np.concatenate(parts, -1) @ self.w["inp.0.weight"].T + self.w["inp.0.bias"]
        mu = x.mean(-1, keepdims=True)
        var = ((x - mu) ** 2).mean(-1, keepdims=True)
        return (x - mu) / np.sqrt(var + 1e-5) * self.w["inp.1.weight"] + self.w["inp.1.bias"]

    def _lstm(self, x: np.ndarray) -> np.ndarray:
        """Hidden state after each step; x shape (T, D). PyTorch gate order: i, f, g, o."""
        wi, wh = self.w["enc.weight_ih_l0"], self.w["enc.weight_hh_l0"]
        b = self.w["enc.bias_ih_l0"] + self.w["enc.bias_hh_l0"]
        hdim = wh.shape[1]
        pre = x @ wi.T + b
        h = np.zeros(hdim, dtype=np.float32)
        c = np.zeros(hdim, dtype=np.float32)
        out = np.empty((len(x), hdim), dtype=np.float32)
        for t in range(len(x)):
            g = pre[t] + wh @ h
            i, f_, gg, o = np.split(g, 4)
            c = _sigmoid(f_) * c + _sigmoid(i) * np.tanh(gg)
            h = _sigmoid(o) * np.tanh(c)
            out[t] = h
        return out

    def _head(self, h: np.ndarray, q_out: np.ndarray, sk_out: np.ndarray) -> np.ndarray:
        parts = [h, self._bag("skill_out.emb.weight", sk_out)]
        if self.use_question:
            parts.append(self.w["q_out.weight"][q_out])
        z = np.maximum(
            np.concatenate(parts, -1) @ self.w["head.0.weight"].T + self.w["head.0.bias"], 0
        )
        logit = (z @ self.w["head.3.weight"].T + self.w["head.3.bias"])[..., 0]
        if self.use_question:
            logit = logit + self.w["q_bias.weight"][q_out][..., 0]
        return _sigmoid(logit)

    # ------------------------------------------------------------ public API

    def predict_sequence(self, q_in, sk_in, r_in, f_in, q_out, sk_out) -> np.ndarray:
        """Index-level API (used by the parity test): P(correct) for each next attempt."""
        h = self._lstm(
            self._inputs(np.asarray(q_in), np.asarray(sk_in), np.asarray(r_in), np.asarray(f_in))
        )
        return self._head(h, np.asarray(q_out), np.asarray(sk_out))

    def state(self, history: list[Attempt]) -> np.ndarray | None:
        """Hidden state after a student's chronological history; None if there is none."""
        if not history:
            return None
        q = np.array([self.q_index(a.question_id) for a in history], dtype=np.int64)
        sk = np.stack([self.skill_row(a.skill_ids) for a in history])
        r = np.array([int(a.correct) for a in history], dtype=np.int64)
        f = np.array(
            [
                [
                    np.log1p(min(a.hints, 10)),
                    float(a.saw_answer),
                    np.log1p(max(a.seconds_since_previous, 0)) / 10,
                ]
                for a in history
            ],
            dtype=np.float32,
        )
        return self._lstm(self._inputs(q, sk, r, f))[-1]

    def predict_questions(
        self, h: np.ndarray, questions: list[tuple[int, list[int]]]
    ) -> np.ndarray:
        """P(correct) for each candidate (question_id, skill_ids) given state h."""
        if h is None:
            raise ValueError("no history: run a diagnostic first")
        q = np.array([self.q_index(qid) for qid, _ in questions], dtype=np.int64)
        sk = np.stack([self.skill_row(s) for _, s in questions])
        hh = np.broadcast_to(h, (len(questions), h.shape[0]))
        return self._head(hh, q, sk)
