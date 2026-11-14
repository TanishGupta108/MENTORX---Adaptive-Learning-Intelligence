"""Ordering questions: key recovery from correct answers, checking, display and seeding.

The data shapes copy FoundationalASSIST: the stored "answer" equals the options (in no
particular order), typed answers join items with " , ", options can be MathML."""

from __future__ import annotations

from fractions import Fraction

import pandas as pd
import pytest

from app.tutor import answers, ordering
from app.tutor.ai import wrong_signature
from app.tutor.seed import build_items

MATH = '<p><math xmlns="http://www.w3.org/1998/Math/MathML">{}</math></p>'


def frac(n: int, d: int, sign: str = "") -> str:
    return MATH.format(f"{sign}<mfrac><mn>{n}</mn><mn>{d}</mn></mfrac>")


def test_plain_items_with_commas_inside_are_recovered():
    # items contain ", " themselves: the options can only be split using the answers
    opts = "(2, 4) and (2, 10), (7, 0) and (7, -9), (1, 1) and (1, 2)"
    good = "(1, 1) and (1, 2) , (2, 4) and (2, 10) , (7, 0) and (7, -9)"
    r = ordering.recover(opts, "<p>Order from closest to farthest apart.</p>", [good] * 25)
    assert r.reason is None
    assert [r.options[i] for i in r.order] == [
        "(1, 1) and (1, 2)",
        "(2, 4) and (2, 10)",
        "(7, 0) and (7, -9)",
    ]


def test_separator_variants_count_as_the_same_answer():
    opts = "Hydrogen, Argon, Chlorine"
    ans = ["Hydrogen , Argon , Chlorine"] * 15 + ["Hydrogen, Argon, Chlorine"] * 10
    r = ordering.recover(opts, "<p>Order by boiling point.</p>", ans)
    assert r.order == [0, 1, 2] and r.agreeing == 25


def test_mathml_numbers_match_by_value_and_must_agree_with_the_sort():
    opts = ", ".join(
        [frac(1, 2, "<mo>-</mo>"), MATH.format("<mn>1</mn>"), frac(1, 2), MATH.format("<mn>0</mn>")]
    )
    q = "<p>Order these numbers from least to greatest:</p>"
    good = "-1/2 , 0 , 1/2 , 1"
    r = ordering.recover(opts, q, [good] * 30)
    assert r.reason is None and r.order == [0, 3, 2, 1]
    # if the students' majority contradicts the arithmetic, nothing is trusted
    wrong = "0 , -1/2 , 1/2 , 1"
    bad = ordering.recover(opts, q, [wrong] * 30)
    assert bad.order is None and bad.reason == "students_disagree_with_numeric_order"


def test_values_of_mathml_text():
    assert ordering.value_of_text("-1(1)/(2)") == Fraction(-3, 2)
    assert ordering.value_of_text("(49)/(100)") == Fraction(49, 100)
    assert ordering.value_of_text("-(3)/(8)") == Fraction(-3, 8)
    assert ordering.value_of_text("|-2.7|") == Fraction(27, 10)
    assert ordering.value_of_text("Person 3") is None


@pytest.mark.parametrize(
    ("answers_given", "reason"),
    [
        (["x , y , z"] * 5, "too_few_correct_answers (5)"),
        (["C. , A. , B."] * 30, "answers_given_as_letters"),
        (["x , y , z"] * 12 + ["z , y , x"] * 12, "no_clear_majority"),
    ],
)
def test_weak_or_unusable_evidence_is_refused(answers_given, reason):
    r = ordering.recover("x, y, z", "<p>Order them.</p>", answers_given)
    assert r.order is None and r.reason == reason


def test_checking_and_showing_an_ordering_answer():
    key = ["2", "0", "1"]
    assert answers.check("ordering", key, {"choices": ["2", "0", "1"]})
    assert not answers.check("ordering", key, {"choices": ["0", "2", "1"]})
    with pytest.raises(ValueError):  # an item missing: not graded, the question isn't used up
        answers.check("ordering", key, {"choices": ["2", "0"]})
    with pytest.raises(ValueError):
        answers.check("ordering", key, {"choice": "2"})
    opts = [{"id": "0", "html": "zero"}, {"id": "1", "html": "one"}, {"id": "2", "html": "two"}]
    shown = answers.describe_key("ordering", key, opts)
    assert shown == {"type": "ordering", "option_ids": key, "options_html": ["two", "zero", "one"]}


def test_two_different_wrong_orders_never_share_an_ai_explanation():
    a, b = {"choices": ["1", "0", "2"]}, {"choices": ["0", "1", "2"]}
    assert wrong_signature(a, ordered=True) != wrong_signature(b, ordered=True)
    # ticked options (check all that apply) are a set: order doesn't matter there
    assert wrong_signature(a) == wrong_signature(b)


@pytest.mark.parametrize("key", [[0, 1, 2, 3], [3, 2, 1, 0], [2, 0, 3, 1]])
def test_items_are_never_shown_already_in_order(key):
    shown = ordering.display_order(4, key, seed=7)
    assert shown not in (key, key[::-1]) and sorted(shown) == [0, 1, 2, 3]


def _problem(pid: int, options: str, body: str) -> dict:
    return {
        "Problem Set Id": "PSO",
        "Problem Part": 1,
        "Problem Type": "Order / Sort",
        "Answer Types": "Ordering",
        "Problem Body": body,
        "Fill-in Options": options,
        "Fill-in Answers": options,  # what the dataset stores: no real key
        "Multiple Choice Options": None,
        "Multiple Choice Answers": None,
        "problem_id": pid,
    }


def test_seed_serves_recovered_orders_and_excludes_the_rest():
    problems = pd.DataFrame(
        [
            _problem(1, "Wyoming, California, Louisiana", "<p>Order by lowest elevation.</p>"),
            _problem(2, "x, y, z", "<p>Order them.</p>"),
            _problem(3, "a, b, c", "<p>Order them.</p>"),
        ]
    )
    skills = pd.DataFrame(
        [
            {"problem_id": p, "skill_id": 129, "node_code": "6.NS.C.7b", "node_name": "n"}
            for p in (1, 2, 3)
        ]
    )
    correct = {1: ["California , Louisiana , Wyoming"] * 25, 2: ["x , y , z"] * 3}
    rows = {r.item["id"]: r.item for r in build_items(problems, skills, {}, None, correct)}
    one = rows[1]
    assert one["answer_type"] == "ordering" and one["exclusion_reason"] is None
    by_id = {o["id"]: o["html"] for o in one["options"]}
    assert [by_id[k] for k in one["answer_key"]] == ["California", "Louisiana", "Wyoming"]
    assert [o["id"] for o in one["options"]] != one["answer_key"]  # not shown pre-solved
    assert rows[2]["exclusion_reason"].startswith("ordering_key_not_recovered: too_few")
    assert rows[3]["exclusion_reason"].startswith("ordering_key_not_recovered")
    # without Interactions.csv nothing is guessed
    none = build_items(problems, skills, {}, None, None)
    assert all(r.item["exclusion_reason"] == "ordering_key_needs_interactions_csv" for r in none)


def test_ai_hints_for_ordering_never_name_the_items():
    from app.tutor.ai import correct_text, leaks_answer
    from app.tutor.models import Item

    item = Item(
        answer_type="ordering",
        answer_key=["1", "0", "2"],
        options=[
            {"id": "0", "html": "<p>-1</p>"},
            {"id": "1", "html": "<p>-4.2</p>"},
            {"id": "2", "html": "<p>3.5</p>"},
        ],
        body_html="<p>Order from least to greatest.</p>",
        media=None,
    )
    assert correct_text(item) == "in this order: -4.2 , -1 , 3.5"
    assert leaks_answer(item, "Start with -4.2, it is furthest left.")
    assert not leaks_answer(item, "Picture a number line: further left means smaller.")


def test_questions_that_need_an_earlier_part_are_excluded(monkeypatch):
    from app.tutor import seed

    monkeypatch.setattr(seed, "NEEDS_EARLIER_PART", {2: "these numbers are in part 1"})
    problems = pd.DataFrame(
        [
            {**_problem(pid, "", "<p>x</p>"), "Answer Types": "Multiple Choice",
             "Problem Body": "<p>If these numbers are temperatures, which is coldest?</p>",
             "Multiple Choice Options": "-3 || 1", "Multiple Choice Answers": "-3"}
            for pid in (1, 2)
        ]
    )  # fmt: skip
    skills = pd.DataFrame(
        [
            {"problem_id": p, "skill_id": 129, "node_code": "6.NS.C.7b", "node_name": "n"}
            for p in (1, 2)
        ]
    )
    rows = {r.item["id"]: r.item for r in build_items(problems, skills, {}, None, {})}
    assert rows[1]["exclusion_reason"] is None
    assert rows[2]["exclusion_reason"] == "needs_earlier_part"
