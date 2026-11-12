"""Safe parsing and comparison of typed maths answers ("2(x-1)", "3/2x+2", "36pi", "sqrt(18)").

Student input is untrusted, and SymPy's parser evaluates Python code, so nothing reaches it
unchecked: the text is tokenised against a strict allowlist (digits, single-letter variables,
+ - * / ^ ( ) = and the names sqrt, cbrt, pi), rebuilt from those tokens, length-limited and
guarded against exponent towers before it is parsed with a minimal namespace.

Conventions follow ASSISTments: "3/2x" means (3/2)x, letters next to each other multiply
("dd4" = 4d^2), "^" is a power and letters are case-insensitive.

Equivalence is decided by evaluating both expressions at several fixed rational points
(exact arithmetic, then a 30-digit numeric comparison), which is fast and does not depend on
SymPy's simplifier. A separate "form" check (sum of n terms vs a single product/term) is used
when a question asks for a particular form ("factor", "expand", "fewer terms").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sympy
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

MAX_LEN = 60
FUNCTIONS = ("sqrt", "cbrt", "pi")
_TOKEN = re.compile(r"[a-z]+|\d+\.\d*|\.\d+|\d+|[+\-*/^()=]|\s+")
_TRANSFORMS = (*standard_transformations, implicit_multiplication_application, convert_xor)
_GLOBALS = {
    "Integer": sympy.Integer,
    "Float": sympy.Float,
    "Rational": sympy.Rational,
    "Symbol": sympy.Symbol,
    "Add": sympy.Add,  # used by the unevaluated parse
    "Mul": sympy.Mul,
    "Pow": sympy.Pow,
    "sqrt": sympy.sqrt,
    "cbrt": sympy.cbrt,
    "pi": sympy.pi,
}
# distinct, "unlucky-proof" rational test points (one value per variable per trial)
_POINTS = [
    [sympy.Rational(7, 3), sympy.Rational(-5, 4), sympy.Rational(11, 7), sympy.Rational(13, 5)],
    [sympy.Rational(17, 6), sympy.Rational(3, 11), sympy.Rational(-9, 7), sympy.Rational(5, 2)],
    [sympy.Rational(-4, 3), sympy.Rational(19, 5), sympy.Rational(2, 9), sympy.Rational(23, 8)],
]


@dataclass(frozen=True)
class Parsed:
    value: sympy.Expr  # evaluated
    form: tuple  # ("sum", n_terms) or ("term",), from the unevaluated parse


def normalize(text: str) -> str:
    """Unicode and spacing clean-up shared by every typed answer."""
    s = str(text).strip()
    for a, b in (
        ("−", "-"),
        ("–", "-"),
        ("×", "*"),
        ("·", "*"),
        ("÷", "/"),
        ("π", "pi"),
        ("√", "sqrt"),
        ("²", "^2"),
        ("³", "^3"),
    ):
        s = s.replace(a, b)
    return s


def _rebuild(text: str) -> str | None:
    """The input rebuilt from allowlisted tokens only, or None if anything else is present."""
    s = normalize(text).lower()
    s = re.sub(r"(?<=\d),(?=\d{3}(\D|$))", "", s)  # thousands separators
    if not s or len(s) > MAX_LEN:
        return None
    tokens = _TOKEN.findall(s)
    if "".join(tokens) != s:
        return None
    out: list[str] = []
    for t in tokens:
        if t.isspace():
            continue
        if t.isalpha():
            words, i = [], 0
            while i < len(t):  # greedy: known names first, otherwise one-letter variables
                name = next((f for f in FUNCTIONS if t.startswith(f, i)), None)
                if name:
                    words.append(name)
                    i += len(name)
                else:
                    words.append(t[i])
                    i += 1
            out.append("*".join(words))
        else:
            out.append(t)
    rebuilt = " ".join(out)
    # no exponent towers or huge exponents (they could take forever to evaluate)
    if rebuilt.count("^") > 3 or re.search(r"\^\s*\(?\s*-?\s*\d{3,}", rebuilt):
        return None
    if re.search(r"\^[^+\-*/=]*\^", rebuilt):
        return None
    return rebuilt


def _form(e: sympy.Basic) -> tuple:
    return ("sum", len(e.args)) if isinstance(e, sympy.Add) else ("term",)


def parse(text: str) -> Parsed | None:
    """Parse one expression (no "="). None if it isn't a valid, safe expression."""
    s = _rebuild(text)
    if s is None or "=" in s:
        return None
    letters = {c: sympy.Symbol(c) for c in set(re.findall(r"\b[a-z]\b", s))}
    try:
        value = parse_expr(
            s, local_dict=letters, global_dict=dict(_GLOBALS), transformations=_TRANSFORMS
        )
        raw = parse_expr(
            s,
            local_dict=letters,
            global_dict=dict(_GLOBALS),
            transformations=_TRANSFORMS,
            evaluate=False,
        )
    except Exception:  # noqa: BLE001 - any parse failure just means "not an expression"
        return None
    if not isinstance(value, sympy.Expr) or len(value.free_symbols) > 4:
        return None
    return Parsed(value=value, form=_form(raw))


def parse_equation(text: str) -> tuple[Parsed, Parsed] | None:
    parts = normalize(text).split("=")
    if len(parts) != 2:
        return None
    left, right = parse(parts[0]), parse(parts[1])
    return (left, right) if left and right else None


def _num(e: sympy.Expr, subs: dict) -> complex | None:
    try:
        v = complex(sympy.N(e.subs(subs), 30))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if v != v or abs(v) == float("inf"):  # nan / inf
        return None
    return v


def equivalent(a: sympy.Expr, b: sympy.Expr) -> bool:
    """Same value at every test point (variables get distinct rational values)."""
    syms = sorted(a.free_symbols | b.free_symbols, key=str)
    if len(syms) > 4:
        return False
    for pts in _POINTS:
        subs = dict(zip(syms, pts, strict=False))
        va, vb = _num(a, subs), _num(b, subs)
        if va is None or vb is None:
            return False
        if abs(va - vb) > 1e-9 * max(1.0, abs(vb)):
            return False
    return True


def value(text: str) -> sympy.Expr | None:
    """A number-only expression's exact value ("43/.5", "11^3", "29+(-13)"); None otherwise."""
    p = parse(text)
    if p is None or p.value.free_symbols:
        return None
    return p.value


def close(a: sympy.Expr, b: sympy.Expr, rel: float = 1e-6) -> bool:
    va, vb = _num(a, {}), _num(b, {})
    return va is not None and vb is not None and abs(va - vb) <= rel * max(1.0, abs(vb))
