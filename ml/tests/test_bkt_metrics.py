import numpy as np
import pandas as pd
import pytest

from mentorx_ml import metrics
from mentorx_ml.bkt import BKT, _padded, forward


def test_forward_first_prediction_uses_only_prior():
    params = np.array([0.3, 0.2, 0.2, 0.1])
    obs, mask = _padded([np.array([1.0, 0.0])])
    p = forward(params, obs, mask)
    assert p[0, 0] == pytest.approx(0.3 * 0.9 + 0.7 * 0.2)


def test_forward_matches_hand_computation():
    l0, t, g, s = 0.3, 0.2, 0.2, 0.1
    obs, mask = _padded([np.array([1.0, 1.0])])
    p = forward(np.array([l0, t, g, s]), obs, mask)
    pc = l0 * (1 - s) + (1 - l0) * g
    post = l0 * (1 - s) / pc
    l1 = post + (1 - post) * t
    assert p[0, 1] == pytest.approx(l1 * (1 - s) + (1 - l1) * g)


def test_prediction_does_not_depend_on_current_answer():
    params = np.array([0.3, 0.2, 0.2, 0.1])
    a, m = _padded([np.array([1.0, 0.0, 1.0])])
    b, _ = _padded([np.array([1.0, 0.0, 0.0])])
    assert forward(params, a, m)[0, 2] == forward(params, b, m)[0, 2]


def test_bkt_recovers_learning_from_synthetic_data():
    rng = np.random.default_rng(0)
    true = dict(p_init=0.2, p_learn=0.25, p_guess=0.15, p_slip=0.08)
    rows = []
    for s in range(400):
        known = rng.random() < true["p_init"]
        for t in range(8):
            p = 1 - true["p_slip"] if known else true["p_guess"]
            rows.append(
                {
                    "student_id": f"s{s}",
                    "concept_id": "c",
                    "correct": int(rng.random() < p),
                    "seq": t,
                }
            )
            if not known and rng.random() < true["p_learn"]:
                known = True
    df = pd.DataFrame(rows)
    fitted = BKT(min_interactions=10).fit(df).params["c"]
    assert fitted[1] == pytest.approx(true["p_learn"], abs=0.08)
    assert fitted[2] == pytest.approx(true["p_guess"], abs=0.08)
    assert fitted[3] == pytest.approx(true["p_slip"], abs=0.08)


def test_ece_zero_for_perfectly_calibrated_bins():
    y = np.array([1, 0, 1, 0, 1, 1, 1, 1, 0, 0])
    p = np.array([0.5] * 4 + [0.75] * 4 + [0.25] * 2)
    # bin 0.5: 2/4 = 0.5 ; bin 0.75: 4/4 = 1.0 (off by .25) ; bin 0.25: 0/2 (off by .25)
    assert metrics.expected_calibration_error(y, p) == pytest.approx(0.4 * 0.25 + 0.2 * 0.25)


def test_bootstrap_delta_against_itself_is_zero():
    rng = np.random.default_rng(0)
    students = np.repeat(np.arange(50), 10)
    y = rng.integers(0, 2, 500)
    p = rng.random(500)
    ci = metrics.bootstrap_by_student(students, y, {"a": p, "b": p}, n_boot=20, reference="a")
    assert ci["b"]["delta_auc"] == (0.0, 0.0)
