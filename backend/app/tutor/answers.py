"""Answer keys and answer checking. Runs on the server only; keys never reach the client.

Supported answer types (everything else is excluded from serving):
- numeric: one blank. The dataset separates alternative accepted answers with ", " (comma +
  space) while "1,000" uses a bare comma as a thousands separator. Students may type
  decimals, fractions ("3/4") or mixed numbers ("1 1/2"); values are compared exactly.
- multiple_choice: one correct option (dataset "Drop Down" questions are served this way).
- check_all: the selected set must equal the correct set exactly.
- ordering: every item, in exactly the correct order (`choices` is the student's order).
- algebraic: an expression or equation, compared by mathematical equivalence (mathexpr.py).
  When the question asks for a form ("factor", "expand", "fewer terms", ...) the answer must
  also have the key's form, so copying the original expression back isn't accepted.
- numeric_expression: a number or an arithmetic expression ("43/.5"); compared by value.
- exact_fraction: the fraction exactly as written (2/6 and 1/3 are different answers unless
  both are listed); "1 1/2" and "1  1/2" are the same.
- exact_match: the dataset's literal answers (case and spacing ignored); numbers compared by
  value, and short algebraic answers ("8x", "-3y+12x") by equivalence and form.

Keys of the typed answer kinds are stored as {"alts": [...], "form": bool}.

Numeric acceptance policy (numeric, and the numeric paths of numeric_expression and
exact_match; V = exact key value, S = the student's value, d = decimals the student typed):
1. The exact value is always accepted, in any form (fraction, mixed number, decimal, ...).
2. Truncated keys are recovered: a key written with >= 6 decimals (e.g. -1.333333333) whose
   simplest nearby fraction F (denominator <= 1000) is non-terminating and rounds back to the
   key is treated as F (-4/3), which is then accepted exactly too.
3. Rounded decimals, only for non-terminating values and when no fraction is asked for: a
   plain decimal with d >= 2 is accepted if the true value rounded (half up) to d places equals
   it (3.67, 3.667 for 11/3; 3.66 and 3.7 stay wrong). Never for terminating values.
4. An explicit rounding instruction in the question ("nearest tenth", "two decimal places",
   "nearest whole percent", ...) wins: S with >= n decimals is accepted when S rounded to n
   places equals the key (or the key rounded to n places).
5. "Write your answer as a fraction": exact values only (rule 3 off).
6. Percent: when the question mentions % or "percent", a trailing % is just a unit (22% == 22);
   otherwise 50% means 0.5.
7. Harmless input is cleaned first: "$", "x =", "1 000", "- 3", "(5)", and a trailing unit
   that the question itself uses, in any spelling ("3.67 pounds" or "3.67 lbs" for a question
   about pounds). A unit the question doesn't use ("12 feet" when it asks for inches) is not
   guessed: the answer is returned unread with "Type just the number, without ...", so the
   student can retype it and the question isn't used up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

from app.tutor import mathexpr
from app.tutor.html import plain_text

TEXT_TYPES = ("algebraic", "numeric_expression", "exact_fraction", "exact_match")
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}
FORM_WORDS = re.compile(
    r"\b(factor|expand|fewer terms|combine like terms|simplif|simplest form|distributive)",
    re.IGNORECASE,
)
INPUT_HINTS = {
    "numeric": "Type a number, a fraction like 11/3, or a decimal rounded to 2 places.",
    "algebraic": "e.g. 3x+2, 2(x-1), x^2, 5/2x, sqrt(7) or 36pi",
    "numeric_expression": "a number or a calculation, e.g. 18.2 or 43/0.5",
    "exact_fraction": "a fraction, e.g. 3/8 or 2 1/4",
    "exact_match": "type your answer",
}


def excel_date_fraction(text: str) -> str | None:
    """Spreadsheet software turned some fraction answers into dates when the dataset was
    exported: "7/24" became "24-Jul" and "7/45" became "Jul-45". Undo exactly that."""
    s = str(text).strip().lower()
    m = re.fullmatch(r"(\d{1,2})-([a-z]{3})", s)
    if m and m.group(2) in MONTHS:
        return f"{MONTHS[m.group(2)]}/{int(m.group(1))}"
    m = re.fullmatch(r"([a-z]{3})-(\d{2})", s)
    if m and m.group(1) in MONTHS:
        return f"{MONTHS[m.group(1)]}/{int(m.group(2))}"
    return None


def split_alternatives(raw: str) -> list[str]:
    """Alternatives are separated by comma + space ("12.5, 12.50"); bare commas stay
    (thousands separators, lists like "1,3,7,21", points like "(4,1)")."""
    return [a.strip() for a in re.split(r",\s+", str(raw).strip()) if a.strip()]


def fraction_form(text: str) -> str | None:
    """Canonical written form of a fraction or mixed number: "3/8", "-2 1/35"."""
    s = re.sub(r"\s+", " ", mathexpr.normalize(text)).strip()
    m = re.fullmatch(r"([+-]?)\s*(\d+) (\d+)\s*/\s*(\d+)", s) or re.fullmatch(
        r"([+-]?)\s*()(\d+)\s*/\s*(\d+)", s
    )
    if not m:
        return None
    sign = "-" if m.group(1) == "-" else ""
    whole = f"{int(m.group(2))} " if m.group(2) else ""
    return f"{sign}{whole}{int(m.group(3))}/{int(m.group(4))}"


def _flat(text: str) -> str:
    return re.sub(r"\s+", "", mathexpr.normalize(plain_text(text))).casefold()


def text_key(kind: str, raw: str, question_html: str = "") -> dict | None:
    """Key for a typed-answer question, or None if the dataset answer can't be used."""
    alts = []
    for a in split_alternatives(raw):
        a = excel_date_fraction(a) or a
        if a.startswith("#"):  # spreadsheet errors such as "#NAME?"
            continue
        if re.search(r"\s[x]\s", a):  # "d x 4 x d": x used as a times sign
            continue
        alts.append(a)
    if kind == "algebraic":
        alts = [a for a in alts if mathexpr.parse(a) or mathexpr.parse_equation(a)]
    elif kind == "numeric_expression":
        alts = [a for a in alts if mathexpr.value(a) is not None]
    elif kind == "exact_fraction":
        alts = [f for f in (fraction_form(a) for a in alts) if f]
    if not alts:
        return None
    form = kind == "algebraic" and bool(FORM_WORDS.search(plain_text(question_html)))
    return {"alts": sorted(dict.fromkeys(alts)), "form": form}


def _algebra_match(alt: str, response: str, form: bool) -> bool:
    if "=" in alt:
        ka, ra = mathexpr.parse_equation(alt), mathexpr.parse_equation(response)
        if not ka or not ra:
            return False
        k = ka[0].value - ka[1].value
        r = ra[0].value - ra[1].value
        return mathexpr.equivalent(k, r) or mathexpr.equivalent(k, -r)
    if "=" in response:  # "y = 3x + 2" for the expression "3x + 2"
        parts = response.split("=")
        if len(parts) == 2 and re.fullmatch(r"\s*[A-Za-z]\s*", parts[0]):
            response = parts[1]
        else:
            return False
    k, r = mathexpr.parse(alt), mathexpr.parse(response)
    if not k or not r or not mathexpr.equivalent(k.value, r.value):
        return False
    return not form or k.form == r.form


def check_text(kind: str, key: dict, response: str, question_html: str = "") -> bool:
    """Raises ValueError for input that can't be read (so the question isn't used up)."""
    ctx = question_context(question_html)
    response = str(response or "").strip()
    if not response:
        raise ValueError("Type your answer first.")
    alts, form = key.get("alts", []), bool(key.get("form"))
    if kind == "algebraic":
        if not (mathexpr.parse(response) or "=" in response):
            raise ValueError(
                "We couldn't read that expression. Use numbers, letters, + - * / ^ and brackets, "
                "for example 3x+2, 2(x-1) or x^2."
            )
        return any(_algebra_match(a, response, form) for a in alts)
    if kind == "numeric_expression":
        sn = student_number(response, ctx)
        if sn is not None:
            keys = [k for k in (parse_number(a) for a in alts) if k is not None]
            if keys and numeric_accepts(keys, sn, ctx):
                return True
        v = mathexpr.value(response)
        if v is None:
            if sn is not None:
                return False
            raise ValueError("Enter a number or a calculation, for example 18.2 or 43/0.5.")
        return any(mathexpr.close(mathexpr.value(a), v) for a in alts)
    if kind == "exact_fraction":
        f = fraction_form(response)
        if f is None:
            raise ValueError("Enter a fraction such as 3/8, or a mixed number such as 2 1/4.")
        return f in alts
    if kind == "exact_match":
        flat = _flat(response)
        sn = student_number(response, ctx)
        for a in alts:
            if _flat(a) == flat:
                return True
            ka = parse_number(a)
            if ka is not None and sn is not None and numeric_accepts([ka], sn, ctx):
                return True
            is_algebra = re.search(r"[\d+\-*/^]", a) and re.search(r"[a-z]", a, re.I)
            if is_algebra and _algebra_match(a, response, form=True):
                return True
        return False
    raise ValueError("This question type isn't supported.")


_NUM = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")


def parse_number(value: str) -> Fraction | None:
    """Exact value of '12', '-0.5', '1,000', '3/4', '1 1/2', '50%'; None if not a number."""
    s = str(value).strip().replace("−", "-").replace("–", "-")
    s = re.sub(r"(?<=\d),(?=\d{3}(\D|$))", "", s)  # thousands separators only
    percent = s.endswith("%")
    if percent:
        s = s[:-1].strip()
    try:
        m = re.fullmatch(r"([+-]?)(\d+)\s+(\d+)\s*/\s*(\d+)", s)  # mixed number
        if m:
            sign = -1 if m.group(1) == "-" else 1
            val = sign * (Fraction(int(m.group(2))) + Fraction(int(m.group(3)), int(m.group(4))))
        elif re.fullmatch(r"[+-]?\d+\s*/\s*\d+", s):
            num, den = (part.strip() for part in s.split("/"))
            val = Fraction(int(num), int(den))
        elif _NUM.match(s):
            val = Fraction(s)
        else:
            return None
    except (ValueError, ZeroDivisionError):
        return None
    return val / 100 if percent else val


def split_options(raw: str) -> list[str]:
    return [o.strip() for o in str(raw).split("||") if o.strip()]


def numeric_key(raw: str) -> list[str] | None:
    """Accepted numeric answers as exact fraction strings; None if any can't be parsed.
    Spreadsheet damage in the export is undone first ("6-May" was 5/6, "1E+12" is 10^12)."""

    def one(a: str) -> Fraction | None:
        a = excel_date_fraction(a) or a
        if re.fullmatch(r"[+-]?\d+(\.\d+)?[eE][+-]?\d{1,2}", a.strip()):
            return Fraction(a.strip())
        return parse_number(a)

    vals = [one(a) for a in re.split(r",\s+", str(raw).strip()) if a.strip()]
    if not vals or any(v is None for v in vals):
        return None
    return sorted({str(v) for v in true_values(vals)})


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", plain_text(text)).strip().casefold()


def choice_key(options_raw: list[str], answers_raw: list[str]) -> list[str] | None:
    """Indices (as option ids "0","1",...) of the correct options; None if any is missing."""
    norm = [_norm(o) for o in options_raw]
    ids = []
    for a in answers_raw:
        try:
            ids.append(str(norm.index(_norm(a))))
        except ValueError:
            return None
    return sorted(set(ids)) if ids else None


def check(answer_type: str, key: list[str] | dict, response: dict, question_html: str = "") -> bool:
    """True if the student's response matches the key. Raises ValueError on a malformed response.
    `question_html` (the item body) lets the numeric policy read rounding/fraction/percent/unit
    instructions; without it only the generic rules apply."""
    if answer_type in TEXT_TYPES:
        return check_text(answer_type, key, str(response.get("value", "")), question_html)
    if answer_type == "numeric":
        ctx = question_context(question_html)
        sn = student_number(str(response.get("value", "")), ctx)
        if sn is None:
            raise ValueError("Enter a number, for example 12, 0.5, 3/4 or 1 1/2.")
        return numeric_accepts([Fraction(k) for k in key], sn, ctx)
    if answer_type == "multiple_choice":
        choice = response.get("choice")
        if not isinstance(choice, str):
            raise ValueError("Choose one option.")
        return [choice] == key
    if answer_type == "check_all":
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("Select at least one option.")
        return sorted({str(c) for c in choices}) == key
    if answer_type == "ordering":
        order = response.get("choices")
        if not isinstance(order, list) or sorted(str(c) for c in order) != sorted(key):
            raise ValueError("Put every item in order, then submit.")
        return [str(c) for c in order] == list(key)
    raise ValueError("This question type isn't supported.")


def describe_key(answer_type: str, key: list[str] | dict, options: list[dict]) -> dict:
    """The correct answer in a form the client can show AFTER the student has answered."""
    if answer_type in TEXT_TYPES:
        alts = list(key.get("alts", []))
        nums = [parse_number(a) for a in alts]
        if answer_type == "numeric_expression" and alts and all(n is not None for n in nums):
            return {"type": "text", "values": shown_values(nums)[:4]}
        return {"type": "text", "values": alts[:4]}
    if answer_type == "numeric":
        return {"type": "numeric", "values": shown_values([Fraction(k) for k in key])}
    if answer_type == "ordering":  # the items in the correct order
        html = {o["id"]: o["html"] for o in options}
        return {"type": "ordering", "option_ids": list(key), "options_html": [html[k] for k in key]}
    return {
        "type": answer_type,
        "option_ids": key,
        "options_html": [o["html"] for o in options if o["id"] in key],
    }


# ---------------------------------------------------------------- numeric policy (see module doc)

GENERIC_UNITS = {
    "cm", "m", "km", "mm", "in", "inch", "inches", "ft", "foot", "feet", "yd", "yard", "yards",
    "mi", "mile", "miles", "g", "gram", "grams", "kg", "mg", "lb", "lbs", "pound", "pounds",
    "oz", "ounce", "ounces", "l", "liter", "liters", "litre", "litres", "ml", "s", "sec",
    "secs", "second", "seconds", "min", "mins", "minute", "minutes", "h", "hr", "hrs", "hour",
    "hours", "dollar", "dollars", "cent", "cents", "degree", "degrees", "°", "unit", "units",
    "square", "sq", "cubic", "meter", "meters", "metre", "metres",
}  # fmt: skip
# spellings of the same unit: a typed unit counts only when the question uses that unit
_UNIT_GROUPS = [
    {"cm", "centimeter", "centimeters", "centimetre", "centimetres"},
    {"m", "meter", "meters", "metre", "metres"},
    {"km", "kilometer", "kilometers", "kilometre", "kilometres"},
    {"mm", "millimeter", "millimeters", "millimetre", "millimetres"},
    {"in", "inch", "inches"},
    {"ft", "foot", "feet"},
    {"yd", "yard", "yards"},
    {"mi", "mile", "miles"},
    {"g", "gram", "grams"},
    {"kg", "kilogram", "kilograms"},
    {"mg", "milligram", "milligrams"},
    {"lb", "lbs", "pound", "pounds"},
    {"oz", "ounce", "ounces"},
    {"l", "liter", "liters", "litre", "litres"},
    {"ml", "milliliter", "milliliters", "millilitre", "millilitres"},
    {"s", "sec", "secs", "second", "seconds"},
    {"min", "mins", "minute", "minutes"},
    {"h", "hr", "hrs", "hour", "hours"},
    {"dollar", "dollars", "$", "money"},  # "money" only ever comes from the question
    {"cent", "cents", "¢"},
    {"degree", "degrees", "°"},
    {"unit", "units"},
]
_UNIT_OF = {w: i for i, g in enumerate(_UNIT_GROUPS) for w in g}
_UNIT_MODIFIERS = {"square", "sq", "cubic"}
_AMBIGUOUS_UNITS = {"in", "m", "s", "h", "l", "g", "min"}  # count only right after a number
_ROUNDING = (
    (0, r"\bnearest\s+whole\b|\bnearest\s+(integer|dollar)\b"),
    (1, r"\bnearest\s+tenths?\b|\b(one|1)\s+decimal\s+(place|point)|\btenths\s+place\b"),
    (
        2,
        r"\bnearest\s+hundredths?\b|\b(two|2)\s+decimal\s+places?\b|\bhundredths\s+place\b"
        r"|\bnearest\s+cent\b",
    ),
    (
        3,
        r"\bnearest\s+thousandths?\b|\b(three|3)\s+decimal\s+places?\b"
        r"|\bthousandths\s+place\b",
    ),
)
_AS_FRACTION = re.compile(
    r"\b(write|express|give|enter|leave)\b[^.?!]{0,30}\bas\s+an?\s+(\w+\s+)?fraction"
    r"|\bfraction\s+form\b|\bas\s+an?\s+(simplified\s+|improper\s+)?fraction\b",
    re.IGNORECASE,
)
_BLANK_SPLIT = re.compile(r'<span class="answer-blank"[^>]*>.*?</span>|<ast-r\b[^>]*>', re.I)


@dataclass(frozen=True)
class QuestionContext:
    percent: bool = False  # the question talks about percent: "22%" means 22
    fraction_required: bool = False  # "write your answer as a fraction": no rounded decimals
    round_to: frozenset[int] = frozenset()  # decimals asked for by an explicit instruction
    units: frozenset[str] = frozenset()  # words right after the answer blank
    known: bool = False  # built from a real question (NO_CONTEXT: the question is unknown)
    unit_groups: frozenset[int] = frozenset()  # units (any spelling) the question mentions


NO_CONTEXT = QuestionContext()


@lru_cache(maxsize=4096)
def question_context(question_html: str) -> QuestionContext:
    if not question_html:
        return NO_CONTEXT
    text = re.sub(r"\s+", " ", plain_text(question_html)).casefold()
    round_to = frozenset(n for n, pat in _ROUNDING if re.search(pat, text))
    parts = _BLANK_SPLIT.split(question_html, maxsplit=1)
    after = plain_text(parts[1]).casefold() if len(parts) > 1 else ""
    units = frozenset(re.findall(r"[a-z°]+", after)[:3])
    groups = {
        _UNIT_OF[w]
        for num, w in re.findall(r"(\d\s*)?([a-z°$¢]+)", text)
        if w in _UNIT_OF and (num or w not in _AMBIGUOUS_UNITS)  # "in" is also a word
    }
    groups |= {_UNIT_OF[c] for c in "$¢°" if c in text}
    return QuestionContext(
        percent="%" in text or "percent" in text,
        fraction_required=bool(_AS_FRACTION.search(text)),
        round_to=round_to,
        units=units,
        known=True,
        unit_groups=frozenset(groups),
    )


@dataclass(frozen=True)
class StudentNumber:
    value: Fraction
    decimals: int | None  # digits after the point of a plain decimal/integer; None otherwise


_PLAIN = re.compile(r"^[+-]?(\d+(\.(\d*))?|\.(\d+))$")
_UNIT_TAIL = re.compile(
    r"^(.*?\d\.?)\s*((?:sq\.?|square|cubic)?\s*[a-z°]+\.?(?:\^?[23]|[²³])?)$", re.IGNORECASE
)


def _strip_unit(s: str, ctx: QuestionContext) -> str:
    m = _UNIT_TAIL.match(s)
    if not m:
        return s
    tail = m.group(2).strip().casefold().rstrip(".")
    tail = re.sub(r"(\^?[23]|[²³])$", "", tail).strip()
    words = [w for w in re.split(r"[\s.]+", tail) if w]
    if not words or not all(w in GENERIC_UNITS or w in ctx.units for w in words):
        return s
    named = [w for w in words if w not in _UNIT_MODIFIERS and w not in ctx.units]
    if ctx.known and any(_UNIT_OF.get(w) not in ctx.unit_groups for w in named):
        # "12 feet" when the question is about inches: don't guess, ask for the number alone
        raise ValueError(f"Type just the number, without “{m.group(2).strip()}”.")
    return m.group(1).strip()


def _unwrap(s: str) -> str:
    if len(s) >= 2 and s[0] == "(" and s[-1] == ")" and "(" not in s[1:-1]:
        return s[1:-1].strip()
    return s


def clean_numeric_input(text: str, ctx: QuestionContext = NO_CONTEXT) -> str:
    """Remove harmless decoration around a number: "$", "x =", a unit, "1 000", "- 3", "(5)"."""
    s = mathexpr.normalize(str(text or "")).strip()
    s = re.sub(r"^[A-Za-z]\s*=\s*", "", s)  # "x = 5"
    s = _unwrap(s)
    s = re.sub(r"^([+-]?)\s*\$\s*", r"\1", s)  # "$1,000", "-$5"
    s = _unwrap(_strip_unit(s, ctx))
    s = re.sub(r"^([+-])\s+(?=[\d.])", r"\1", s)  # "- 3"
    if "/" not in s and re.fullmatch(r"[+-]?\d{1,3}( \d{3})+(\.\d+)?", s):
        s = s.replace(" ", "")  # "1 000"
    return s


def student_number(text: str, ctx: QuestionContext = NO_CONTEXT) -> StudentNumber | None:
    """The student's number (after clean-up), or None if it isn't one."""
    s = clean_numeric_input(text, ctx)
    if ctx.percent and s.endswith("%"):
        s = s[:-1].strip()  # the percent sign is just the unit here
    value = parse_number(s)
    if value is None:
        return None
    plain = _PLAIN.match(re.sub(r"(?<=\d),(?=\d{3}(\D|$))", "", s))
    decimals = None
    if plain:
        frac = plain.group(3) if plain.group(3) is not None else plain.group(4)
        decimals = len(frac or "")
    return StudentNumber(value, decimals)


def terminating(v: Fraction) -> bool:
    d = v.denominator
    for p in (2, 5):
        while d % p == 0:
            d //= p
    return d == 1


def decimals_of(v: Fraction) -> int | None:
    """Digits after the point of a terminating value (0.25 -> 2); None if non-terminating."""
    if not terminating(v):
        return None
    n = 0
    while (v * 10**n).denominator != 1:
        n += 1
    return n


def round_half_up(v: Fraction, d: int) -> Fraction:
    scaled = abs(v) * 10**d
    r = int(scaled + Fraction(1, 2))  # floor(x + 1/2): halves round away from zero
    return Fraction(r if v >= 0 else -r, 10**d)


def recover(v: Fraction) -> Fraction | None:
    """The exact value behind a truncated repeating decimal key (-1.333333333 -> -4/3)."""
    d = decimals_of(v)
    if d is None or (d < 6 and v.denominator < 10**6):
        return None
    f = v.limit_denominator(1000)
    if f == v or terminating(f) or round_half_up(f, d) != v:
        return None
    return f


def true_values(keys: list[Fraction]) -> list[Fraction]:
    """Key values plus the exact values recovered from truncated keys."""
    out = list(dict.fromkeys(keys))
    for k in keys:
        f = recover(k)
        if f is not None and f not in out:
            out.append(f)
    return out


def numeric_accepts(keys: list[Fraction], sn: StudentNumber, ctx: QuestionContext) -> bool:
    exact = true_values(keys)
    if sn.value in exact:
        return True
    if sn.decimals is None:
        return False
    if ctx.round_to:
        return any(
            sn.decimals >= n and round_half_up(sn.value, n) in (v, round_half_up(v, n))
            for n in ctx.round_to
            for v in exact
        )
    if ctx.fraction_required or sn.decimals < 2:
        return False
    return any(not terminating(v) and round_half_up(v, sn.decimals) == sn.value for v in exact)


def decimal_text(v: Fraction) -> str:
    """A terminating value written as a plain decimal ("0.0082", "-3", "1000")."""
    d = decimals_of(v) or 0
    sign = "-" if v < 0 else ""
    n = abs(v.numerator) * 10**d // v.denominator
    if d == 0:
        return f"{sign}{n}"
    whole, frac = divmod(n, 10**d)
    return f"{sign}{whole}.{frac:0{d}d}"


def mixed_text(v: Fraction) -> str | None:
    """11/3 -> "3 2/3"; None for proper fractions and integers."""
    if v.denominator == 1 or abs(v) < 1:
        return None
    sign = "-" if v < 0 else ""
    whole, rest = divmod(abs(v.numerator), v.denominator)
    return f"{sign}{whole} {rest}/{v.denominator}"


def shown_values(keys: list[Fraction]) -> list[str]:
    """Correct answers for display: exact form first, with a rounded hint for repeating values
    ("11/3 (about 3.67)"); truncated keys and rounded copies of a repeating value are dropped."""
    exact = true_values(keys)
    truncated = {k for k in keys if recover(k) is not None}
    repeating = [v for v in exact if not terminating(v)]
    out: list[str] = []
    for v in sorted(exact, key=lambda v: (terminating(v), v)):
        if v in truncated:
            continue
        if not terminating(v):
            out.append(f"{v} (about {decimal_text(round_half_up(v, 2))})")
            continue
        d = decimals_of(v) or 0
        if d >= 1 and any(round_half_up(r, d) == v for r in repeating):
            continue  # "0.83" next to 5/6
        out.append(decimal_text(v))
    return out


def accepted_number_forms(keys: list[Fraction]) -> set[Fraction]:
    """Every value the checker would accept without an instruction (for the AI leak check)."""
    out = set(true_values(keys))
    for v in list(out):
        if not terminating(v):
            out.update(round_half_up(v, d) for d in (2, 3, 4))
    return out
