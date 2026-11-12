"""Answer keys and answer checking. Runs on the server only; keys never reach the client.

Supported answer types (everything else is excluded from serving):
- numeric: one blank. The dataset separates alternative accepted answers with ", " (comma +
  space) while "1,000" uses a bare comma as a thousands separator. Students may type
  decimals, fractions ("3/4") or mixed numbers ("1 1/2"); values are compared exactly.
- multiple_choice: one correct option (dataset "Drop Down" questions are served this way).
- check_all: the selected set must equal the correct set exactly.
- algebraic: an expression or equation, compared by mathematical equivalence (mathexpr.py).
  When the question asks for a form ("factor", "expand", "fewer terms", ...) the answer must
  also have the key's form, so copying the original expression back isn't accepted.
- numeric_expression: a number or an arithmetic expression ("43/.5"); compared by value.
- exact_fraction: the fraction exactly as written (2/6 and 1/3 are different answers unless
  both are listed); "1 1/2" and "1  1/2" are the same.
- exact_match: the dataset's literal answers (case and spacing ignored); numbers compared by
  value, and short algebraic answers ("8x", "-3y+12x") by equivalence and form.

Keys of the typed answer kinds are stored as {"alts": [...], "form": bool}.
"""

from __future__ import annotations

import re
from fractions import Fraction

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
    "numeric": "e.g. 12, 0.5, 3/4 or 1 1/2",
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


def check_text(kind: str, key: dict, response: str) -> bool:
    """Raises ValueError for input that can't be read (so the question isn't used up)."""
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
        v = mathexpr.value(response)
        if v is None:
            raise ValueError("Enter a number or a calculation, for example 18.2 or 43/0.5.")
        return any(mathexpr.close(mathexpr.value(a), v) for a in alts)
    if kind == "exact_fraction":
        f = fraction_form(response)
        if f is None:
            raise ValueError("Enter a fraction such as 3/8, or a mixed number such as 2 1/4.")
        return f in alts
    if kind == "exact_match":
        flat = _flat(response)
        for a in alts:
            if _flat(a) == flat:
                return True
            ka, kr = parse_number(a), parse_number(response)
            if ka is not None and kr is not None and ka == kr:
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
    return sorted({str(v) for v in vals})


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


def check(answer_type: str, key: list[str] | dict, response: dict) -> bool:
    """True if the student's response matches the key. Raises ValueError on a malformed response."""
    if answer_type in TEXT_TYPES:
        return check_text(answer_type, key, str(response.get("value", "")))
    if answer_type == "numeric":
        value = parse_number(str(response.get("value", "")))
        if value is None:
            raise ValueError("Enter a number, for example 12, 0.5, 3/4 or 1 1/2.")
        return str(value) in key
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
    raise ValueError("This question type isn't supported.")


def describe_key(answer_type: str, key: list[str] | dict, options: list[dict]) -> dict:
    """The correct answer in a form the client can show AFTER the student has answered."""
    if answer_type in TEXT_TYPES:
        return {"type": "text", "values": list(key.get("alts", []))[:4]}
    if answer_type == "numeric":
        shown = []
        for k in key:
            f = Fraction(k)
            shown.append(str(f.numerator) if f.denominator == 1 else f"{float(f):g} ({k})")
        return {"type": "numeric", "values": shown}
    return {
        "type": answer_type,
        "option_ids": key,
        "options_html": [o["html"] for o in options if o["id"] in key],
    }
