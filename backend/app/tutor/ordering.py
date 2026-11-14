"""Ordering ("Order / Sort") questions: recovering the correct order from real answers.

FoundationalASSIST stores no key for these questions: for all 32 of them the "Fill-in Answers"
column is identical to "Fill-in Options", the items in an arbitrary order (e.g. 5429 lists
-2.1, -4.2, -1.5, ... for "least to greatest"). The order is recovered from what students who
were marked correct actually typed (Interactions.csv, `discrete_score == 1`), and only when
that evidence is strong:

- at least MIN_CORRECT correct answers, of which at least MIN_AGREEMENT give one same order
  (separators and spacing ignored);
- every item of that answer matches exactly one option, by its text or, for numbers written
  as formulas, by its exact value; answers given as letters ("C. , A. , B.") are never used,
  because the letters followed a display order we don't have;
- if every option is a number and the question says which way to sort ("least to greatest",
  "greatest to least", ...), the recovered order must be that sort: two independent sources
  must agree.

Anything else stays excluded, with a reason. Nothing is guessed.
"""

from __future__ import annotations

import html as html_lib
import itertools
import random
import re
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction

from app.tutor import answers
from app.tutor.html import math_text, sanitize

MIN_CORRECT = 20
MIN_AGREEMENT = 0.6
MAX_PLAIN_ITEMS = 8  # plain-text items are matched by trying orders (8! = 40,320)

_ASCENDING = (
    r"least to greatest|smallest to largest|lowest to highest|least to most|shortest to longest"
)
_DESCENDING = (
    r"greatest to least|largest to smallest|highest to lowest|most to least|longest to shortest"
)


@dataclass(frozen=True)
class Recovered:
    options: list[str]  # raw option HTML, in the dataset's order
    order: list[int] | None  # option indices in the correct order, or None
    reason: str | None  # why there is no key
    correct: int = 0  # correct student answers seen
    agreeing: int = 0  # of which gave the recovered order


def _norm(text: str) -> str:
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", str(text)))
    text = text.replace("−", "-").replace("–", "-")
    return re.sub(r"\s+", " ", text).strip().casefold()


def answer_tokens(answer: str) -> list[str]:
    """Items of a typed ordering answer. ASSISTments joined them with " , ", which never
    occurs inside an item (items like "(7, 0) and (7, -9)" contain ", " without the space
    before the comma)."""
    return [t.strip() for t in str(answer).split(" , ")]


def _answer_key(answer: str) -> str:
    """Comparable form of an answer: both separators (" , " and ", ") and spacing ignored."""
    return _norm(str(answer).replace(" , ", ", "))


def value_of(raw_html: str) -> Fraction | None:
    """Exact value of an option written as text or MathML: "-1(1)/(2)" -> -3/2, "|-2.7|" -> 27/10."""
    text = math_text(sanitize(raw_html)) if "<" in raw_html else html_lib.unescape(raw_html)
    return value_of_text(text)


def value_of_text(text: str) -> Fraction | None:
    s = re.sub(r"\s+", " ", str(text)).strip()
    s = s.replace("−", "-").replace("–", "-")
    # MathML text: a whole part right before a fraction is a mixed number: -1(1)/(2) -> -1 1/2
    s = re.sub(r"^(-?\d+)\s*\((\d+)\)\s*/\s*\((\d+)\)$", r"\1 \2/\3", s)
    s = re.sub(r"\((\d+)\)\s*/\s*\((\d+)\)", r"\1/\2", s)  # (49)/(100) -> 49/100
    m = re.fullmatch(r"\|\s*(.+?)\s*\|", s)
    if m:
        inner = answers.parse_number(m.group(1))
        return abs(inner) if inner is not None else None
    return answers.parse_number(s)


def split_options(raw: str, tokens: list[str]) -> list[str] | None:
    """The options of the question. HTML options are split between tags; plain-text items may
    contain ", " themselves, so the plain list is rebuilt from the answer's own items."""
    raw = str(raw).strip()
    if raw.startswith("<"):
        parts = [p.strip() for p in re.split(r"(?<=>)\s*,\s+(?=<)", raw) if p.strip()]
        return parts if len(parts) == len(tokens) else None
    if len(tokens) > MAX_PLAIN_ITEMS:
        return None
    by_text = {_norm(t): t for t in tokens}
    if len(by_text) != len(tokens):
        return None
    for perm in itertools.permutations(tokens):
        if ", ".join(perm) == raw:
            return list(perm)
    return None


def _direction(question_html: str) -> str | None:
    text = _norm(question_html)
    up, down = re.search(_ASCENDING, text), re.search(_DESCENDING, text)
    if up and not down:
        return "asc"
    if down and not up:
        return "desc"
    return None


def _match(options: list[str], tokens: list[str]) -> list[int] | None:
    """Option index of each answer item: by text, else (all numbers) by exact value."""
    if len(options) != len(tokens):
        return None
    texts = [_norm(o) for o in options]
    if len(set(texts)) == len(texts) and sorted(texts) == sorted(_norm(t) for t in tokens):
        return [texts.index(_norm(t)) for t in tokens]
    values = [value_of(o) for o in options]
    typed = [value_of_text(t) for t in tokens]
    if None in values or None in typed or len(set(values)) != len(values):
        return None
    if sorted(values) != sorted(typed):
        return None
    return [values.index(v) for v in typed]


def recover(options_raw: str, question_html: str, correct_answers: list[str]) -> Recovered:
    """The correct order for one ordering question (see the module doc for the rules)."""
    n = len(correct_answers)
    if n < MIN_CORRECT:
        return Recovered([], None, f"too_few_correct_answers ({n})", n)
    counts = Counter(_answer_key(a) for a in correct_answers)
    top_key, agreeing = counts.most_common(1)[0]
    if agreeing / n < MIN_AGREEMENT:
        return Recovered([], None, "no_clear_majority", n, agreeing)
    # tokenise a member of the top group that uses the unambiguous " , " separator
    members = [a for a in correct_answers if _answer_key(a) == top_key]
    spaced = [a for a in members if " , " in a]
    if not spaced:
        return Recovered([], None, "answer_items_not_separable", n, agreeing)
    tokens = answer_tokens(spaced[0])
    if all(re.fullmatch(r"[A-Za-z]\.?", t) for t in tokens):
        return Recovered([], None, "answers_given_as_letters", n, agreeing)
    options = split_options(options_raw, tokens)
    if options is None:
        return Recovered([], None, "options_not_matched", n, agreeing)
    order = _match(options, tokens)
    if order is None:
        return Recovered(options, None, "items_not_matched_to_options", n, agreeing)
    values = [value_of(o) for o in options]
    if all(v is not None for v in values):
        direction = _direction(question_html)
        if direction is None:
            return Recovered(options, None, "numeric_order_direction_unclear", n, agreeing)
        expected = sorted(range(len(values)), key=lambda i: values[i], reverse=direction == "desc")
        if order != expected:
            return Recovered(options, None, "students_disagree_with_numeric_order", n, agreeing)
    return Recovered(options, order, None, n, agreeing)


def display_order(n: int, key_order: list[int], seed: int) -> list[int]:
    """The order the items are shown in: the dataset's own order, unless that already is the
    answer (or its reverse); then a fixed shuffle that is neither."""
    shown = list(range(n))
    if shown not in (key_order, key_order[::-1]):
        return shown
    rng = random.Random(seed)
    for _ in range(100):
        rng.shuffle(shown)
        if shown not in (key_order, key_order[::-1]):
            return shown
    return shown
