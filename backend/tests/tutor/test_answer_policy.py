"""Numeric answer policy (audit 1.6 cases, verbatim). Items are built in memory with the same
keys and question text as the real ones, so no database is needed."""

from __future__ import annotations

from fractions import Fraction

import pytest

from app.tutor import ai, answers
from app.tutor.html import sanitize
from app.tutor.models import Item

BLANK = '<ast-r type="text" marker="1"></ast-r>'


def q(text: str, after: str = "") -> str:
    """Sanitised question HTML with one answer blank, as stored in items.body_html."""
    return sanitize(f"<p>{text}</p><p>{BLANK} {after}</p>")


def num(key_raw: str, html: str, value: str) -> bool:
    key = answers.numeric_key(key_raw)
    assert key, key_raw
    return answers.check("numeric", key, {"value": value}, html)


STRAWBERRIES = q(
    "Strawberries cost $3.00 per pound. How many pounds of strawberries can you buy for $11.00?",
    "pounds",
)

CASES = [
    # (key, question html, accepted, rejected)
    (
        "11/3",
        STRAWBERRIES,
        ["11/3", "3 2/3", "22/6", "3.67", "3.667", "3.6667", "3.666667", "3.67 pounds"],
        ["4", "3.7", "3.6", "3.66", "3.668", "3.7 pounds"],
    ),
    (
        "-1.333333333",
        q("Solve 3(x-4)=12x"),
        ["-4/3", "-1 1/3", "-1.33", "-1.333", "-1.333333333", "x = -4/3"],
        ["-1.3", "-1", "-1.34", "4/3"],
    ),
    (
        "-0.666666667",
        q("Solve the equation. Write your answer as a fraction."),
        ["-2/3", "-4/6", "-0.666666667"],
        ["-0.67"],
    ),
    ("-0.055555556", q("What is the slope? Write your answer as a fraction."), ["-1/18"], []),
    (
        "5/6, 0.83, 0.833",
        q("What fraction of the pizza is left?"),
        ["0.83", "0.833", "0.8333"],
        ["0.8"],
    ),
    ("9.681", q("What is 9.6 + 0.081?"), ["9.681"], ["9.68", "9.7"]),
    ("0.0082", q("What is 0.082 divided by 10?"), ["0.0082"], ["0.008"]),
    (
        "142.24",
        q("Find the area. Round your answer to two decimal places."),
        ["142.24", "142.240", "142.2399"],
        ["142.2", "142"],
    ),
    ("37/2", q("How long is the side? Round to the nearest tenth."), ["18.5", "18.49"], ["18"]),
    (
        "22",
        q("What percent of the class walks to school? Round to the nearest whole percent.", "%"),
        ["22", "22%", "22.0"],
        ["0.22"],
    ),
    ("1/2", q("What is 1 divided by 2?"), ["50%"], []),
    ("1000", q("How much money did she save?"), ["$1,000", "1 000", "1000 dollars"], []),
    ("5", q("Solve for x: x + 2 = 7"), ["x=5", "(5)"], ["x=6"]),
    ("12", q("How long is the board?", "inches"), ["12 inches", "12 in."], ["11 inches"]),
    ("-3", q("What is 2 - 5?"), ["- 3", "(-3)"], []),
    ("3/2", q("Write 1.5 as a mixed number."), ["1 1/2"], []),
]


@pytest.mark.parametrize("key,html,ok,bad", CASES, ids=[c[0] for c in CASES])
def test_audit_numeric_cases(key, html, ok, bad):
    for v in ok:
        assert num(key, html, v), f"{v!r} should be accepted for key {key}"
    for v in bad:
        assert not num(key, html, v), f"{v!r} should be rejected for key {key}"


def test_a_unit_the_question_does_not_use_is_not_accepted():
    with pytest.raises(ValueError, match="without"):  # asked to retype, not marked right
        num("12", q("How long is the board?", "inches"), "12 feet")
    with pytest.raises(ValueError):
        num("5", q("Solve for x: x + 2 = 7"), "5 cm")


def test_numeric_expression_truncated_key():
    key = answers.text_key("numeric_expression", "-0.533333333")
    for v in ("-8/15", "-0.53", "-0.533"):
        assert answers.check("numeric_expression", key, {"value": v}, q("Evaluate.")), v
    assert not answers.check("numeric_expression", key, {"value": "-0.5"}, q("Evaluate."))
    assert answers.check("numeric_expression", {"alts": ["86"]}, {"value": "43/0.5"})


def test_exact_match_numeric_path_uses_policy():
    key = {"alts": ["11/3"], "form": False}
    assert answers.check("exact_match", key, {"value": "3.67"}, q("How many?"))
    assert not answers.check("exact_match", key, {"value": "3.66"}, q("How many?"))


def test_truncated_key_recovered_at_seed_and_shown_exactly():
    assert answers.numeric_key("-1.333333333") == ["-1333333333/1000000000", "-4/3"]
    shown = answers.describe_key("numeric", answers.numeric_key("-1.333333333"), [])
    assert shown["values"] == ["-4/3 (about -1.33)"]
    assert answers.describe_key("numeric", ["11/3"], [])["values"] == ["11/3 (about 3.67)"]
    assert answers.describe_key("numeric", answers.numeric_key("9.681"), [])["values"] == ["9.681"]
    assert answers.describe_key("numeric", answers.numeric_key("0.0082"), [])["values"] == [
        "0.0082"
    ]
    assert answers.describe_key("numeric", answers.numeric_key("5/6, 0.83, 0.833"), [])[
        "values"
    ] == ["5/6 (about 0.83)"]
    assert answers.describe_key("numeric", ["1000"], [])["values"] == ["1000"]


def test_terminating_keys_never_recovered():
    assert answers.recover(Fraction("9.681")) is None
    assert answers.recover(Fraction("5.64e-07")) is None
    assert answers.recover(Fraction("3.1416")) is None


def test_whole_number_hint_is_not_a_rounding_instruction():
    ctx = answers.question_context(q("If the answer is not a whole number, write it as a decimal."))
    assert ctx.round_to == frozenset()


def test_round_half_up():
    assert answers.round_half_up(Fraction(-4, 3), 2) == Fraction("-1.33")
    assert answers.round_half_up(Fraction(5, 2), 0) == 3
    assert answers.round_half_up(Fraction(-5, 2), 0) == -3


def test_garbage_still_rejected_without_using_the_question():
    with pytest.raises(ValueError):
        answers.check("numeric", ["5"], {"value": "5 apples and 3"}, q("How many?"))
    with pytest.raises(ValueError):
        answers.check("numeric", ["5"], {"value": "abc"}, q("How many?"))


def test_leak_check_counts_rounded_and_mixed_forms():
    item = Item(
        id=1,
        skill_id=1,
        body_html=STRAWBERRIES,
        answer_type="numeric",
        options=[],
        answer_key=["11/3"],
    )
    assert ai.leaks_answer(item, "That is about 3.67 pounds.")
    assert ai.leaks_answer(item, "You get 3 2/3 pounds.")
    assert ai.leaks_answer(item, "Divide 11 by 3 and write it as 3.667.")
    assert ai.leaks_answer(item, "about 3.66667")  # any number of decimals
    assert not ai.leaks_answer(item, "Divide the money you have by the price of one pound.")


def test_leak_check_for_letter_options():
    opts = [{"id": str(i), "html": c} for i, c in enumerate("ABCD")]
    item = Item(
        id=2, skill_id=1, body_html="<p>Where is France?</p>", answer_type="multiple_choice",
        options=opts, answer_key=["1"],
    )  # fmt: skip
    for text in ("Look at letter B.", "It is (B).", "Try option B.", "B is right.", "Pick b.",
                 "Not A, C or D."):  # fmt: skip
        assert ai.leaks_answer(item, text), text
    assert not ai.leaks_answer(item, "A good first step is to find the Atlantic coast.")
    named = Item(
        id=3, skill_id=1, body_html="<p>Name the highlighted country.</p>",
        answer_type="multiple_choice",
        options=[{"id": "0", "html": "Spain"}, {"id": "1", "html": "France"}], answer_key=["1"],
    )  # fmt: skip
    assert ai.leaks_answer(named, "This is France, famous for Paris.")
    assert not ai.leaks_answer(named, "Look for a country that borders Spain.")
