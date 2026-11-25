"""The LSTM + Attention knowledge-tracing model (dkt_q_attn) as the server runs it."""

from __future__ import annotations

import json

import numpy as np

from app.ml.dkt import Attempt, KTInference
from tests.tutor.conftest import ARTIFACTS

GEO = ARTIFACTS.parent / "geography"


def _model() -> KTInference:
    return KTInference.from_artifacts(ARTIFACTS, "dkt_q_attn")


def _history(meta: dict, n: int, seed: int = 0) -> list[Attempt]:
    rng = np.random.default_rng(seed)
    qs, sks = meta["question_ids"], meta["skill_ids"]
    return [
        Attempt(
            int(qs[rng.integers(len(qs))]),
            [int(sks[rng.integers(len(sks))])],
            bool(rng.integers(2)),
            int(rng.integers(3)),
            bool(rng.random() < 0.1),
            float(rng.integers(5, 300)),
        )
        for _ in range(n)
    ]


def test_maths_serves_the_attention_model_and_geography_keeps_its_own():
    meta = json.loads((ARTIFACTS / "kt_meta.json").read_text())
    assert meta["default_model"] == "dkt_q_attn"
    m = meta["models"]["dkt_q_attn"]
    assert m["architecture"] == "lstm_attn" and m["parity_max_abs_diff"] < 1e-4
    assert m["parity_detail"]["serving_path"] < 1e-4  # state() + predict_questions() checked too
    assert KTInference.from_artifacts(ARTIFACTS).name == "dkt_q_attn"
    assert KTInference.from_artifacts(GEO).name == "dkt_q"  # no default_model: stays DKT-Q


def test_serving_path_equals_the_sequence_path():
    """state(history[:k]) + predict_questions(next) == the training-layout prediction at k-1."""
    meta = json.loads((ARTIFACTS / "kt_meta.json").read_text())
    model = _model()
    hist = _history(meta, 40)
    q = np.array([model.q_index(a.question_id) for a in hist])
    sk = np.stack([model.skill_row(a.skill_ids) for a in hist])
    r = np.array([int(a.correct) for a in hist])
    f = np.array(
        [
            [
                np.log1p(min(a.hints, 10)),
                float(a.saw_answer),
                np.log1p(a.seconds_since_previous) / 10,
            ]
            for a in hist
        ],
        dtype=np.float32,
    )
    seq = model.predict_sequence(q[:-1], sk[:-1], r[:-1], f[:-1], q[1:], sk[1:])
    for k in (1, 7, 25, 39):
        h = model.state(hist[:k])
        assert h.shape == (k, 128)  # attention keeps every earlier state
        p = model.predict_questions(h, [(hist[k].question_id, hist[k].skill_ids)])[0]
        assert abs(p - seq[k - 1]) < 1e-5


def test_attention_never_sees_the_answer_it_predicts():
    meta = json.loads((ARTIFACTS / "kt_meta.json").read_text())
    model = _model()
    hist = _history(meta, 20, seed=1)
    q = np.array([model.q_index(a.question_id) for a in hist])
    sk = np.stack([model.skill_row(a.skill_ids) for a in hist])
    r = np.array([int(a.correct) for a in hist])
    f = np.zeros((20, 3), dtype=np.float32)
    base = model.predict_sequence(q[:-1], sk[:-1], r[:-1], f[:-1], q[1:], sk[1:])
    r2 = r.copy()
    r2[10] = 1 - r2[10]  # flip attempt 10
    flipped = model.predict_sequence(q[:-1], sk[:-1], r2[:-1], f[:-1], q[1:], sk[1:])
    assert np.allclose(base[:10], flipped[:10], atol=1e-6)  # predictions of attempts 1..10
    assert not np.allclose(base[10:], flipped[10:])  # later predictions do use it


def test_chunked_scoring_matches_one_by_one_and_history_matters():
    meta = json.loads((ARTIFACTS / "kt_meta.json").read_text())
    model = _model()
    h = model.state(_history(meta, 30, seed=2))
    cands = [
        (int(q), [int(meta["skill_ids"][i % 50])])
        for i, q in enumerate(meta["question_ids"][:1100])
    ]
    allp = model.predict_questions(h, cands)  # crosses the 1024-candidate chunk boundary
    assert allp.dtype == np.float32 and np.isfinite(allp).all()
    for i in (0, 1023, 1024, 1099):
        assert abs(model.predict_questions(h, [cands[i]])[0] - allp[i]) < 1e-5
    for sk in (130, 166, 217, 198):  # real skills; question ids unknown to the model
        good = model.state(
            [Attempt(-i, [sk], True, seconds_since_previous=90) for i in range(1, 7)]
        )
        bad = model.state(
            [Attempt(-i, [sk], False, seconds_since_previous=90) for i in range(1, 7)]
        )
        p_good = model.predict_questions(good, [(-99, [sk])])[0]
        p_bad = model.predict_questions(bad, [(-99, [sk])])[0]
        assert 0 < p_bad + 0.2 < p_good < 1, "a correct history must predict clearly higher success"
    assert model.state([]) is None


def test_a_forced_model_a_subject_lacks_falls_back_to_its_default(monkeypatch):
    from app.core.config import get_settings
    from app.tutor import kt

    monkeypatch.setattr(get_settings(), "kt_model", "dkt_q_attn")
    kt.reset_cache()
    try:
        assert kt.get_model("MATH").name == "dkt_q_attn"
        assert kt.get_model("GEO").name == "dkt_q"  # Geography has no attention export
        monkeypatch.setattr(get_settings(), "kt_model", "dkt_q")
        kt.reset_cache()
        assert kt.get_model("MATH").name == "dkt_q"  # an explicit choice still wins
    finally:
        kt.reset_cache()
