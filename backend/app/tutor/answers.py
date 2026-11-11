"""Answer keys and answer checking. Runs on the server only; keys never reach the client.

Supported answer types (everything else is excluded from serving):
- numeric: one blank. The dataset separates alternative accepted answers with ", " (comma +
  space) while "1,000" uses a bare comma as a thousands separator. Students may type
  decimals, fractions ("3/4") or mixed numbers ("1 1/2"); values are compared exactly.
- multiple_choice: one correct option.
- check_all: the selected set must equal the correct set exactly.
"""

from __future__ import annotations

import re
from fractions import Fraction

from app.tutor.html import plain_text

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
    """Accepted numeric answers as exact fraction strings; None if any can't be parsed."""
    vals = [parse_number(a) for a in re.split(r",\s+", str(raw).strip()) if a.strip()]
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


def check(answer_type: str, key: list[str], response: dict) -> bool:
    """True if the student's response matches the key. Raises ValueError on a malformed response."""
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


def describe_key(answer_type: str, key: list[str], options: list[dict]) -> dict:
    """The correct answer in a form the client can show AFTER the student has answered."""
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
