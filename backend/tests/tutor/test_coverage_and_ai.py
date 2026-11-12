"""Typed answers, dataset images, multi-skill questions, the adaptive diagnostic, Mixed
practice, streaks, spaced revision, the AI tutor and live model monitoring."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from app.core.config import get_settings
from app.tutor import answers, llm, mathexpr
from app.tutor.html import math_text, resolve_image_url, sanitize, scan_images
from tests.conftest import auth, register
from tests.tutor.conftest import SKILLS, answer_body, make_dataset

# ---------------------------------------------------------------- typed answers


@pytest.mark.parametrize(
    "key,question,response,ok",
    [
        ("2(13a-5)", "Factor to write an equivalent expression", "2(-5+13a)", True),
        ("2(13a-5)", "Factor to write an equivalent expression", "26a-10", False),  # not factored
        ("2(13a-5)", "Write an equivalent expression", "26a-10", True),  # any form is fine
        ("125/3pi", "", "125pi/3", True),
        ("125/3pi", "", "125π/3", True),
        ("(3/7)x, 3x/7", "", "y = 3x/7", True),
        ("4d^2", "", "dd4", True),
        ("x-2y", "Expand", "-1/2(-2x+4y)", False),
        ("sqrt(18)", "", "3sqrt(2)", True),
        ("a^2+b^2", "", "b^2+a^2", True),
        ("a^2+b^2", "", "a^2-b^2", False),
    ],
)
def test_algebraic_answers(key, question, response, ok):
    k = answers.text_key("algebraic", key, f"<p>{question}</p>")
    assert answers.check("algebraic", k, {"value": response}) is ok


def test_typed_answer_kinds_and_spreadsheet_damage():
    assert answers.numeric_key("6-May") == ["5/6"] and answers.numeric_key("Jan-40") == ["1/40"]
    assert answers.numeric_key("1E+12") == ["1000000000000"]
    frac = answers.text_key("exact_fraction", "24-Jul", "")
    assert answers.check("exact_fraction", frac, {"value": "7/24"})
    assert not answers.check("exact_fraction", frac, {"value": "14/48"})  # exact form required
    expr = answers.text_key("numeric_expression", "43/.5", "")
    assert answers.check("numeric_expression", expr, {"value": "86"})
    assert answers.check("numeric_expression", expr, {"value": "43/0.5"})
    em = answers.text_key("exact_match", "1,3,7,21", "")
    assert answers.check("exact_match", em, {"value": "1, 3, 7, 21"})
    em2 = answers.text_key("exact_match", "8x", "<p>Write it with fewer terms</p>")
    assert answers.check("exact_match", em2, {"value": "8X"})
    assert not answers.check("exact_match", em2, {"value": "10x-2x"})
    assert answers.text_key("algebraic", "#NAME?", "") is None
    assert answers.describe_key("algebraic", em2, [])["type"] == "text"


@pytest.mark.parametrize(
    "evil", ["__import__('os')", "9^9^9^9", "x^99999", "a" * 80, "open('x')", "x;y", "lambda"]
)
def test_expression_parser_is_safe(evil):
    """Only allowlisted tokens reach SymPy; anything else is rejected or harmless."""
    p = mathexpr.parse(evil)
    assert p is None or p.value.free_symbols <= {*map(mathexpr.sympy.Symbol, "abdeilmnoprstxy")}


def test_unreadable_typed_answer_is_rejected_not_marked_wrong():
    k = answers.text_key("algebraic", "2x+1", "")
    with pytest.raises(ValueError):
        answers.check("algebraic", k, {"value": "2x+"})


# ---------------------------------------------------------------- images and formulas


def test_wiris_formula_images_become_mathml():
    wiris = (
        '<img src="/pluginwiris_engine/app/showimage?formula=abc" '
        'data-mathml="«math xmlns=¨http://www.w3.org/1998/Math/MathML¨»«mfrac»«mn»1«/mn»'
        '«mn»2«/mn»«/mfrac»«/math»">'
    )
    out = sanitize(f"<p>Half is {wiris}</p>")
    assert "<img" not in out and "<mfrac><mn>1</mn><mn>2</mn></mfrac>" in out
    assert scan_images(wiris) == ([], 0)  # nothing to check: it is a formula


def test_images_only_from_allowlisted_https_hosts():
    assert resolve_image_url("//resources.assistments.org/fetch/a.png") == (
        "https://resources.assistments.org/fetch/a.png"
    )
    assert resolve_image_url("/images/assistments/1.jpg") == (
        "https://app.assistments.org/images/assistments/1.jpg"
    )
    assert resolve_image_url("https://evil.example.com/x.png") is None
    assert resolve_image_url("javascript:alert(1)") is None
    raw = '<p><img src="//resources.assistments.org/a.png" onerror="x()" width="200"></p>'
    out = sanitize(raw)
    assert 'src="https://resources.assistments.org/a.png"' in out and "onerror" not in out
    assert 'referrerpolicy="no-referrer"' in out and 'width="200"' in out
    assert "<img" not in sanitize(raw, image_ok=lambda u: False)  # unverified -> dropped


def test_math_text_for_the_ai_tutor():
    html = (
        "<p>Solve <math><mfrac><mn>3</mn><mn>4</mn></mfrac><mo>+</mo>"
        '<msup><mi>x</mi><mn>2</mn></msup></math> <span class="answer-blank">?</span></p>'
    )
    text = math_text(html)
    assert "(3)/(4)" in text and "x^(2)" in text and "____" in text


# ---------------------------------------------------------------- seeding new content


def add_rows(folder, image_ok: bool) -> dict:
    """An algebraic question and an image question for skill 129, plus image_check.json."""
    p = pd.read_csv(folder / "Problems.csv")
    s = pd.read_csv(folder / "Skills.csv")
    base = p.iloc[0].to_dict()
    url = "https://resources.assistments.org/fetch/test.png"
    rows = [
        {
            **base,
            "problem_id": 990001,
            "Answer Types": "Algebraic Expression",
            "Problem Body": "<p>Factor 6x+9</p><p><ast-r></ast-r></p>",
            "Fill-in Answers": "3(2x+3)",
        },
        {
            **base,
            "problem_id": 990002,
            "Problem Body": f'<p>Look at <img src="{url}"></p><p><ast-r></ast-r></p>',
        },
    ]
    p = pd.concat([p, pd.DataFrame(rows)], ignore_index=True)
    s = pd.concat(
        [
            s,
            pd.DataFrame(
                [
                    {"problem_id": r["problem_id"], "skill_id": 129, "node_code": "6.RP.A.3a"}
                    | {"node_name": SKILLS[0][2]}
                    for r in rows
                ]
            ),
        ],
        ignore_index=True,
    )
    p.to_csv(folder / "Problems.csv", index=False)
    s.to_csv(folder / "Skills.csv", index=False)
    (folder / "image_check.json").write_text(
        json.dumps({"checked_at": "x", "results": {url: {"ok": image_ok, "detail": "200"}}})
    )
    return {"algebraic": 990001, "image": 990002}


@pytest.mark.parametrize("image_ok", [True, False])
def test_seed_serves_typed_and_verified_image_questions(db, tmp_path, image_ok):
    from app.tutor.models import Item
    from app.tutor.seed import seed_math

    make_dataset(tmp_path / "d")
    ids = add_rows(tmp_path / "d", image_ok)
    summary = seed_math(db, tmp_path / "d", tmp_path / "d" / "artifacts")
    alg, img = db.get(Item, ids["algebraic"]), db.get(Item, ids["image"])
    assert alg.answer_type == "algebraic" and alg.exclusion_reason is None
    assert alg.answer_key == {"alts": ["3(2x+3)"], "form": True}
    assert (img.exclusion_reason is None) is image_ok
    if image_ok:
        assert "<img" in img.body_html
    assert summary["usable_mixed_items"] == 1 and summary["images_checked"]


# ---------------------------------------------------------------- adaptive diagnostic


def run_diagnostic(client, h, keys, correct=lambda q: False):
    a = client.post("/api/v2/assessments", json={"kind": "diagnostic"}, headers=h).json()
    codes = []
    for _ in range(a["total"]):
        q = client.get(f"/api/v2/assessments/{a['id']}/next", headers=h).json()
        assert q["selection"]["how"]  # every question says why it was chosen
        codes.append(q["skill"]["code"])
        r = client.post(
            f"/api/v2/assessments/{a['id']}/answer",
            json=answer_body(keys, q, correct(q)),
            headers=h,
        )
        assert r.status_code == 200, r.text
    return a, codes


def test_adaptive_diagnostic_checks_building_blocks_and_explains_itself(client, math_keys, learner):
    _, codes = run_diagnostic(client, learner, math_keys)  # everything wrong
    assert len(codes) == 10 and len(set(codes)) == 10  # one question per standard
    diag = client.get("/api/v2/diagnosis", headers=learner).json()
    trace = diag["selection_trace"]
    assert [t["position"] for t in trace] == list(range(1, 11))
    assert trace[0]["kind"] == "start" and all(t["correct"] is False for t in trace)
    assert any(t["kind"] == "model" and 0 < t["predicted_p"] < 1 for t in trace)
    # curated links in seeddata: 7.EE.B.4a needs 6.EE.B.7, 7.RP.A.3 needs 6.RP.A.3b
    needs = {"7.EE.B.4a": "6.EE.B.7", "7.RP.A.3": "6.RP.A.3b"}
    probes = 0
    for i, code in enumerate(codes[:-1]):
        if code in needs and needs[code] not in codes[: i + 1] and probes < 2:
            assert trace[i + 1]["kind"] == "prerequisite" and codes[i + 1] == needs[code]
            probes += 1


# ---------------------------------------------------------------- mixed practice


def test_mixed_practice_is_separate_from_skill_evidence(client, math_keys, learner):
    h = learner
    r = client.post("/api/v2/practice", json={"kind": "mixed"}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "mixed_locked"
    run_diagnostic(client, h, math_keys, correct=lambda q: True)
    before = {
        s["id"]: s["attempts"]
        for s in client.get("/api/v2/diagnosis", headers=h).json()["assessed"]
    }
    dash = client.get("/api/v2/dashboard", headers=h).json()
    assert dash["mixed"]["available"] and dash["mixed"]["questions"] == 1
    s = client.post("/api/v2/practice", json={"kind": "mixed"}, headers=h).json()
    assert s["kind"] == "mixed" and s["skill_id"] is None
    q = client.get(f"/api/v2/practice/{s['id']}/next", headers=h).json()
    assert q["mixed"] and len(q["skills"]) == 2
    # the multi-skill test question is a copy of the first numeric question
    value = math_keys[900001]["answer"]
    a = client.post(
        f"/api/v2/practice/{s['id']}/answer",
        json={"item_id": q["item_id"], "value": value},
        headers=h,
    ).json()
    assert a["correct"] and a["interaction_id"]
    after = {
        s["id"]: s["attempts"]
        for s in client.get("/api/v2/diagnosis", headers=h).json()["assessed"]
    }
    assert after == before  # one shared score is never per-skill evidence
    dash = client.get("/api/v2/dashboard", headers=h).json()
    assert dash["mixed"]["answered"] == 1 and dash["mixed"]["accuracy"] == 1.0


# ---------------------------------------------------------------- streaks, goals, revision


def test_streak_and_daily_goal(client, math_keys, learner):
    h = learner
    assert (
        client.patch("/api/v2/profile", json={"daily_goal": 5}, headers=h).json()["daily_goal"] == 5
    )
    assert client.patch("/api/v2/profile", json={"daily_goal": 0}, headers=h).status_code == 422
    run_diagnostic(client, h, math_keys)
    st = client.get("/api/v2/dashboard", headers=h).json()["streak"]
    assert st["current"] == 1 and st["today"] == 10 and st["goal_met"] and st["daily_goal"] == 5


def test_revision_gaps_double():
    from app.tutor.assess import revision_interval

    cfg = get_settings()
    gaps = [revision_interval(n, cfg) for n in range(6)]
    assert gaps[:4] == [7, 14, 28, 56] and max(gaps) == 60


# ---------------------------------------------------------------- AI tutor


class FakeAI(list):
    """Replaces the model: records prompts, returns fixed texts."""

    hint_text = "Think about what adding means."


@pytest.fixture
def fake_ai(monkeypatch):
    fake = FakeAI()

    def complete(messages, max_tokens=1200):
        fake.append(messages[-1]["content"])
        if "first step" in messages[-1]["content"]:  # a hint request
            return fake.hint_text, 5, "test-model"
        return "1. Add the numbers.\n2. Check.\nTip: line them up.", 5, "test-model"

    monkeypatch.setattr(llm, "complete", complete)
    return fake


def _first_practice_answer(client, h, keys, correct: bool):
    s = client.post("/api/v2/practice", json={"skill_id": 129}, headers=h).json()
    q = client.get(f"/api/v2/practice/{s['id']}/next", headers=h).json()
    a = client.post(
        f"/api/v2/practice/{s['id']}/answer", json=answer_body(keys, q, correct), headers=h
    )
    return s, q, a.json()


def test_ai_explanations_are_cached_private_and_after_answering(
    client, math_keys, learner, fake_ai
):
    h = learner
    assert client.get("/api/v2/ai/status", headers=h).json()["enabled"]
    _, q, a = _first_practice_answer(client, h, math_keys, correct=False)
    r = client.post("/api/v2/ai/explain", json={"interaction_id": a["interaction_id"]}, headers=h)
    assert r.status_code == 200 and "Tip:" in r.json()["content"] and not r.json()["cached"]
    assert "AI-generated" in r.json()["label"]
    assert "Correct answer:" in fake_ai[-1] and "The student answered" in fake_ai[-1]
    again = client.post(
        "/api/v2/ai/explain", json={"interaction_id": a["interaction_id"]}, headers=h
    )
    assert again.json()["cached"] and len(fake_ai) == 1  # no second model call
    other = auth(register(client, email="other@example.com"))
    stolen = client.post(
        "/api/v2/ai/explain", json={"interaction_id": a["interaction_id"]}, headers=other
    )
    assert stolen.status_code == 404


def test_ai_hint_never_gives_the_answer_away(client, math_keys, learner, fake_ai):
    h = learner
    s = client.post("/api/v2/practice", json={"skill_id": 129}, headers=h).json()
    q = client.get(f"/api/v2/practice/{s['id']}/next", headers=h).json()
    key = math_keys[q["item_id"]]
    if key["type"] == "numeric":
        fake_ai.hint_text = f"The answer is {key['answer']}."  # a leaking hint
    else:
        fake_ai.hint_text = "The correct answer is option B."
    leak = client.post(f"/api/v2/practice/{s['id']}/hint?ai=true", headers=h).json()
    assert leak["kind"] != "ai" and "note" in leak  # thrown away, skill hint instead
    a = client.post(
        f"/api/v2/practice/{s['id']}/answer", json=answer_body(math_keys, q, True), headers=h
    )
    assert a.json()["hint_used"]  # any hint counts as help for the model's label
    from app.tutor.ai import leaks_answer
    from app.tutor.models import Item

    assert not leaks_answer(
        Item(answer_type="numeric", answer_key=["42"], options=[]), "Try adding first."
    )
    assert leaks_answer(Item(answer_type="numeric", answer_key=["42"], options=[]), "You get 42.")


def test_ai_daily_limit_and_switch_off(client, math_keys, learner, fake_ai, monkeypatch):
    h = learner
    _, _, a = _first_practice_answer(client, h, math_keys, correct=False)
    monkeypatch.setattr(get_settings(), "ai_daily_limit", 0)
    r = client.post("/api/v2/ai/explain", json={"interaction_id": a["interaction_id"]}, headers=h)
    assert r.status_code == 429
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "")
    r = client.post("/api/v2/ai/explain", json={"interaction_id": a["interaction_id"]}, headers=h)
    assert r.status_code == 503 and not client.get("/api/v2/ai/status", headers=h).json()["enabled"]


def test_ai_fallback_models_and_busy_message(monkeypatch):
    tried = []

    def ask(client, model, messages, max_tokens):
        tried.append(model)
        raise llm._Retry

    monkeypatch.setattr(llm, "_ask", ask)
    with pytest.raises(llm.AIUnavailable, match="busy"):
        llm.complete([{"role": "user", "content": "hi"}])
    assert tried == get_settings().ai_models and len(tried) >= 2
    assert llm._clean(r"So \frac{3}{4} = \(x^{2}\)") == "So (3)/(4) = x^2"


# ---------------------------------------------------------------- admin: model monitor, AI texts


def test_admin_model_monitor_and_ai_moderation(client, math_keys, learner, fake_ai, db):
    from app.db.models import User

    run_diagnostic(client, learner, math_keys)
    _, _, a = _first_practice_answer(client, learner, math_keys, correct=False)
    client.post("/api/v2/ai/explain", json={"interaction_id": a["interaction_id"]}, headers=learner)
    admin_h = auth(register(client, email="boss@example.com"))
    assert client.get("/api/v2/admin/model", headers=admin_h).status_code == 403
    db.query(User).filter(User.email == "boss@example.com").update({"role": "admin"})
    db.commit()
    mon = client.get("/api/v2/admin/model", headers=admin_h).json()
    assert mon["overall"]["n"] >= 9  # every answer after the first has a stored prediction
    assert {"assessment", "practice", "mixed_questions"} <= mon["by_context"].keys()
    assert sum(b["n"] for b in mon["calibration"]) == mon["overall"]["n"]
    texts = client.get("/api/v2/admin/ai", headers=admin_h).json()
    assert texts and texts[0]["kind"] == "explanation"
    client.patch(f"/api/v2/admin/ai/{texts[0]['id']}", json={"status": "hidden"}, headers=admin_h)
    hidden = client.post(
        "/api/v2/ai/explain", json={"interaction_id": a["interaction_id"]}, headers=learner
    )
    assert hidden.status_code == 410
