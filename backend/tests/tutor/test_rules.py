"""Unit tests: answer checking, HTML sanitising, diagnosis/mode rules, the 2-up/2-down rule,
and the NumPy model against its recorded PyTorch parity."""

from __future__ import annotations

import json
from fractions import Fraction

import numpy as np
import pytest

from app.ml.dkt import Attempt, KTInference
from app.tutor import answers
from app.tutor.html import count_blanks, sanitize
from app.tutor.practice import adjust
from app.tutor.seed import difficulty_level, standard_url
from app.tutor.state import Evidence, diagnose, learning_mode
from tests.tutor.conftest import ARTIFACTS


@pytest.mark.parametrize(
    "text,value",
    [
        ("12", 12),
        ("-0.5", Fraction(-1, 2)),
        ("1,000", 1000),
        ("3/4", Fraction(3, 4)),
        ("1 1/2", Fraction(3, 2)),
        ("50%", Fraction(1, 2)),
        (" 7 ", 7),
        ("abc", None),
        ("1/0", None),
    ],
)
def test_parse_number(text, value):
    assert answers.parse_number(text) == value


def test_numeric_key_keeps_thousands_and_alternatives():
    key = answers.numeric_key("1,000")
    assert answers.check("numeric", key, {"value": "1000"})
    assert not answers.check("numeric", key, {"value": "1"}), "the comma bug must not come back"
    alt = answers.numeric_key("30.68, 30.69")
    assert answers.check("numeric", alt, {"value": "30.69"}) and not answers.check(
        "numeric", alt, {"value": "30.7"}
    )
    assert answers.check("numeric", answers.numeric_key("0.5"), {"value": "1/2"})


def test_choice_keys_and_check_all():
    key = answers.choice_key(["<p>Radius</p>", "Area", "Diameter"], ["Radius", "Diameter"])
    assert key == ["0", "2"]
    assert answers.check("check_all", key, {"choices": ["2", "0"]})
    assert not answers.check("check_all", key, {"choices": ["0"]})
    with pytest.raises(ValueError):
        answers.check("numeric", ["1"], {"value": "abc"})


def test_sanitize_rebuilds_from_allowlist():
    dirty = '<p style="x" onclick="evil()">Hi <script>alert(1)</script><a href="javascript:x">l</a><img src=x onerror=y></p><math><mfenced><mn>2</mn></mfenced></math><ast-r marker="1"></ast-r>'
    out = sanitize(dirty)
    for bad in ("script", "onclick", "onerror", "href", "<img", "style=", "mfenced"):
        assert bad not in out
    assert "alert(1)" in out  # text survives, escaped, as harmless text
    assert "<mrow><mo>(</mo><mn>2</mn><mo>)</mo></mrow>" in out
    assert "answer-blank" in out and count_blanks(dirty) == 1


def test_difficulty_and_standard_urls():
    assert difficulty_level(0.8, 50) == "easy" and difficulty_level(0.5, 50) == "medium"
    assert difficulty_level(0.3, 50) == "hard" and difficulty_level(0.3, 3) == "unrated"
    assert standard_url("7.EE.B.4a") == "https://www.thecorestandards.org/Math/Content/7/EE/B/4/a/"
    assert standard_url("7.RP.A.3") == "https://www.thecorestandards.org/Math/Content/7/RP/A/3/"


def test_no_evidence_is_never_called_weak_or_strong():
    assert (
        diagnose(Evidence(0, 0, []), predicted=0.05, strength=0.75, weakness=0.45)
        == "needs_assessment"
    )
    assert (
        diagnose(Evidence(0, 0, []), predicted=0.99, strength=0.75, weakness=0.45)
        == "needs_assessment"
    )


def test_diagnosis_needs_evidence_and_model_agreement():
    weak = Evidence(3, 0, [0, 0, 0])
    assert diagnose(weak, 0.3, 0.75, 0.45) == "potential_weakness"
    assert diagnose(weak, 0.9, 0.75, 0.45) == "developing"  # model disagrees -> not labelled weak
    strong = Evidence(4, 4, [1, 1, 1, 1])
    assert diagnose(strong, 0.8, 0.75, 0.45) == "likely_strength"
    assert (
        diagnose(Evidence(1, 1, [1]), 0.9, 0.75, 0.45) == "developing"
    )  # one answer isn't a strength


def test_learning_mode_per_evidence_and_preference():
    assert learning_mode(Evidence(4, 0, [0, 0, 0, 0]), 0.3) == "foundation"
    assert learning_mode(Evidence(6, 6, [1] * 6), 0.9) == "advanced"
    assert learning_mode(Evidence(6, 6, [1] * 6, hints=6), 0.9) == "independent"  # hints lower it
    assert learning_mode(Evidence(4, 2, [1, 0, 1, 0]), 0.5, "challenge") == "independent"
    assert learning_mode(Evidence(0, 0, []), None) == "guided"


def test_two_up_two_down():
    assert adjust("easy", [1, 1]) == ("medium", [], "up")
    assert adjust("medium", [0, 0]) == ("easy", [], "down")
    assert adjust("medium", [1, 0]) == ("medium", [1, 0], None)
    assert adjust("hard", [1, 1])[0] == "hard"  # boundary
    assert adjust("easy", [0, 0])[0] == "easy"  # boundary


def test_numpy_model_loads_and_is_parity_checked():
    meta = json.loads((ARTIFACTS / "kt_meta.json").read_text())
    for name, m in meta["models"].items():
        assert m["parity_max_abs_diff"] < 1e-4, name
    model = KTInference.from_artifacts(ARTIFACTS, "dkt_q")
    for sk in (130, 166, 217, 198):  # real skills; question IDs unknown to the model
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
    assert np.isfinite(model.predict_questions(good, [(meta["question_ids"][0], [130])])).all()
