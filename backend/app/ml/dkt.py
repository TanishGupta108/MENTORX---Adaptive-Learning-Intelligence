"""Knowledge-tracing inference (DKT-Q, DKT-Q + Attention, DKT) in plain NumPy.

The models were trained in PyTorch (ml/notebooks/02_foundationalassist_knowledge_tracing.ipynb,
and ml/notebooks/04_lstm_variants_kaggle.ipynb for the attention variant).
`ml/scripts/export_kt.py` and `ml/scripts/export_kt_attn.py` save their weights as .npz and check
that THIS file reproduces the PyTorch predictions (max difference recorded in kt_meta.json).
Serving without PyTorch keeps the API small enough for a 512 MB host and avoids a 200 MB
dependency.

Input convention (must match training exactly):
- skills: index i+1 = meta.skill_ids[i]; 0 = padding. Up to 3 skills per question.
- questions: index i+1 = meta.question_ids[i] (questions seen by TRAINING students);
  0 = unknown question (the model then relies on its skills only).
- label r = 1 only for a first-attempt correct answer with no hint and the answer not shown.
- per-attempt features: [log1p(min(hints,10)), saw_answer, log1p(seconds since previous)/10].
- position t reads attempts 0..t and predicts attempt t+1.

Architectures (kt_meta.json `architecture`):
- "lstm": the LSTM's last hidden state + the next question's embeddings -> MLP head.
- "lstm_attn": the same, plus multi-head attention whose query is the next question and whose
  keys/values are the LSTM states after EVERY earlier attempt (never the attempt being predicted).
  Its state is therefore the whole (T, D) matrix of hidden states, not one vector.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

MAX_SK = 3
ATTN_CHUNK = 1024  # candidate questions per attention block (bounds memory on a small host)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _layer_norm(x: np.ndarray, weight: np.ndarray, bias: np.ndarray) -> np.ndarray:
    mu = x.mean(-1, keepdims=True)
    var = ((x - mu) ** 2).mean(-1, keepdims=True)
    return (x - mu) / np.sqrt(var + 1e-5) * weight + bias


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
    architecture: str = "lstm"  # "lstm" or "lstm_attn"
    heads: int = 4  # attention heads (lstm_attn only)

    @property
    def uses_attention(self) -> bool:
        return self.architecture == "lstm_attn"

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
        architecture: str = "lstm",
        heads: int = 4,
    ) -> KTInference:
        if architecture not in ("lstm", "lstm_attn"):
            raise ValueError(f"unknown architecture {architecture!r}")
        with np.load(npz_path) as data:
            w = {k.replace("__", "."): data[k].astype(np.float32) for k in data.files}
        return cls(
            w=w,
            use_question=use_question,
            skill_index={int(s): i + 1 for i, s in enumerate(skill_ids)},
            question_index={int(q): i + 1 for i, q in enumerate(question_ids)},
            name=name,
            meta=meta or {},
            architecture=architecture,
            heads=heads,
        )

    @classmethod
    def from_artifacts(cls, artifact_dir: Path | str, name: str | None = None) -> KTInference:
        """Load a model from kt_meta.json; no name = the folder's `default_model` (else dkt_q)."""
        d = Path(artifact_dir)
        meta = json.loads((d / "kt_meta.json").read_text())
        name = name or meta.get("default_model", "dkt_q")
        m = meta["models"][name]
        return cls.from_files(
            d / m["file"],
            m["uses_question_ids"],
            meta["skill_ids"],
            meta["question_ids"],
            name,
            m,
            m.get("architecture", "lstm"),
            int(m.get("heads", 4)),
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
        cnt = np.maximum((idx > 0).sum(-1, keepdims=True), 1).astype(np.float32)  # stay float32
        return e.sum(-2) / cnt

    def _inputs(self, q, sk, r, f) -> np.ndarray:
        sr = np.where(sk > 0, 2 * sk + r[:, None], 0)
        parts = [self._bag("skill_resp.emb.weight", sr)]
        if self.use_question:
            qr = np.where(q > 0, 2 * q + r, 0)
            parts += [self.w["q_resp.weight"][qr], f.astype(np.float32)]
        x = np.concatenate(parts, -1) @ self.w["inp.0.weight"].T + self.w["inp.0.bias"]
        return _layer_norm(x, self.w["inp.1.weight"], self.w["inp.1.bias"])

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

    def _target(self, q_out: np.ndarray, sk_out: np.ndarray) -> list[np.ndarray]:
        """Embeddings of the question to predict (no outcome)."""
        parts = [self._bag("skill_out.emb.weight", sk_out)]
        if self.use_question:
            parts.append(self.w["q_out.weight"][q_out])
        return parts

    def _attend(self, target: np.ndarray, hs: np.ndarray, causal: bool) -> np.ndarray:
        """nn.MultiheadAttention (eval mode) + LayerNorm, as in the trained LSTM+Attn model.

        target: (N, 2D) next-question embeddings; hs: (T, D) LSTM states after each attempt.
        causal=True (training layout, N == T): row t may look at states 0..t only.
        causal=False (serving): every candidate may look at all T states, which all
        come before the attempt being predicted.
        """
        n, (t, d) = len(target), hs.shape
        dh = d // self.heads
        scale = 1.0 / dh**0.5  # a Python float keeps the arrays float32
        wp, bp = self.w["attn.in_proj_weight"], self.w["attn.in_proj_bias"]
        query = target @ self.w["query.weight"].T + self.w["query.bias"]
        q = query @ wp[:d].T + bp[:d]
        k = hs @ wp[d : 2 * d].T + bp[d : 2 * d]
        v = hs @ wp[2 * d :].T + bp[2 * d :]
        ctx = np.empty((n, d), dtype=np.float32)
        cols = np.arange(t)
        # 2-D matmuls per head and chunk: about twice as fast as one batched 3-D matmul,
        # and memory stays at ATTN_CHUNK x T per step whatever the number of candidates.
        for a in range(0, n, ATTN_CHUNK):
            rows = slice(a, min(a + ATTN_CHUNK, n))
            future = cols[None, :] > np.arange(rows.start, rows.stop)[:, None] if causal else None
            for i in range(self.heads):
                c = slice(i * dh, (i + 1) * dh)
                s = q[rows, c] @ k[:, c].T
                s *= scale
                if future is not None:
                    s[future] = -np.inf
                s -= s.max(1, keepdims=True)
                np.exp(s, out=s)
                s /= s.sum(1, keepdims=True)
                ctx[rows, c] = s @ v[:, c]
        out = ctx @ self.w["attn.out_proj.weight"].T + self.w["attn.out_proj.bias"]
        return _layer_norm(out, self.w["attn_norm.weight"], self.w["attn_norm.bias"])

    def _head(
        self,
        h: np.ndarray,
        q_out: np.ndarray,
        sk_out: np.ndarray,
        ctx: np.ndarray | None = None,
    ) -> np.ndarray:
        parts = [h, *self._target(q_out, sk_out)]
        if ctx is not None:
            parts.append(ctx)
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
        q_out, sk_out = np.asarray(q_out), np.asarray(sk_out)
        ctx = None
        if self.uses_attention:
            ctx = self._attend(np.concatenate(self._target(q_out, sk_out), -1), h, causal=True)
        return self._head(h, q_out, sk_out, ctx)

    def state(self, history: list[Attempt]) -> np.ndarray | None:
        """The model's state after a student's chronological history; None if there is none.

        "lstm": the last hidden state, shape (D,). "lstm_attn": the hidden state after every
        attempt, shape (T, D), because attention looks back at all of them. Treat it as opaque
        and pass it to predict_questions()."""
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
        hs = self._lstm(self._inputs(q, sk, r, f))
        return hs if self.uses_attention else hs[-1]

    def predict_questions(
        self, h: np.ndarray, questions: list[tuple[int, list[int]]]
    ) -> np.ndarray:
        """P(correct) for each candidate (question_id, skill_ids) given state h."""
        if h is None:
            raise ValueError("no history: run a diagnostic first")
        q = np.array([self.q_index(qid) for qid, _ in questions], dtype=np.int64)
        sk = np.stack([self.skill_row(s) for _, s in questions])
        if not self.uses_attention:
            hh = np.broadcast_to(h, (len(questions), h.shape[0]))
            return self._head(hh, q, sk)
        ctx = self._attend(np.concatenate(self._target(q, sk), -1), h, causal=False)
        hh = np.broadcast_to(h[-1], (len(questions), h.shape[1]))
        return self._head(hh, q, sk, ctx)
