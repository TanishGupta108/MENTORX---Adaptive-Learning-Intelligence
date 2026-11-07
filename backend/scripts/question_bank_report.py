"""Print a coverage and review-progress report for a subject's question bank.

Usage (from backend/):
    python scripts/question_bank_report.py                  # machine_learning
    python scripts/question_bank_report.py machine_learning --review-sheet review.md

Exit code 1 if the bank doesn't meet the coverage standard, so it can gate CI.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.content.question_bank import (  # noqa: E402
    QUESTION_BANK_DIR,
    QuestionBank,
    QuestionSpec,
    load_question_bank,
)


def _kind(q: QuestionSpec) -> str:
    if q.diagnostic:
        return "diagnostic"
    if q.test_form:
        return f"form {q.test_form}"
    return "practice"


def print_report(bank: QuestionBank) -> None:
    order = bank.topological_order()
    names = {c.code: c.name for c in bank.concepts}
    header = f"{'Concept':<34}{'Total':>6}{'Easy':>6}{'Med':>6}{'Hard':>6}{'Diag':>6}"
    header += f"{'FormA':>7}{'FormB':>7}{'Reviewed':>10}"
    print(f"\n{bank.subject.name} ({bank.subject.code})\n")
    print(header)
    print("-" * len(header))
    for code in order:
        qs = [q for q in bank.questions if q.concept == code]
        practice = Counter(q.difficulty for q in qs if q.is_practice)
        reviewed = sum(q.review_status == "reviewed" for q in qs)
        print(
            f"{names[code]:<34}{len(qs):>6}{practice[1]:>6}{practice[2]:>6}{practice[3]:>6}"
            f"{sum(q.diagnostic for q in qs):>6}"
            f"{sum(q.test_form == 'A' for q in qs):>7}"
            f"{sum(q.test_form == 'B' for q in qs):>7}"
            f"{f'{reviewed}/{len(qs)}':>10}"
        )
    total = len(bank.questions)
    reviewed = sum(q.review_status == "reviewed" for q in bank.questions)
    keys = Counter(q.answer for q in bank.questions)
    print("-" * len(header))
    print(f"Total questions: {total} | reviewed: {reviewed} ({reviewed / total:.0%})")
    print("Answer letters: " + ", ".join(f"{k} {keys[k] / total:.0%}" for k in "ABCD"))

    problems = bank.coverage_problems()
    print("\nCoverage standard: " + ("PASS" if not problems else "FAIL"))
    for p in problems:
        print(f"  - {p}")


def write_review_sheet(bank: QuestionBank, path: Path) -> None:
    """A Markdown sheet a reviewer can read top to bottom, one concept per section."""
    names = {c.code: c.name for c in bank.concepts}
    lines = [f"# Review sheet: {bank.subject.name}", ""]
    lines.append("Tick each box once the question passes every item of the review checklist")
    lines.append("in docs/question-bank-guide.md, then set `review_status: reviewed` in the YAML.")
    lines.append("")
    for code in bank.topological_order():
        lines += [f"## {names[code]} (`{code}`)", ""]
        for q in (q for q in bank.questions if q.concept == code):
            mark = "x" if q.review_status == "reviewed" else " "
            lines.append(f"- [{mark}] **{q.id}** · {_kind(q)} · difficulty {q.difficulty}")
            lines.append(f"  {q.stem}")
            for key, text in q.options.items():
                tick = " ✅" if key == q.answer else ""
                lines.append(f"  - {key}. {text}{tick}")
            lines.append(f"  *Explanation:* {q.explanation}")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReview sheet written to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("subject", nargs="?", default="machine_learning")
    parser.add_argument("--review-sheet", type=Path, help="also write a Markdown review sheet")
    args = parser.parse_args()

    bank = load_question_bank(QUESTION_BANK_DIR / args.subject)
    print_report(bank)
    if args.review_sheet:
        write_review_sheet(bank, args.review_sheet)
    return 1 if bank.coverage_problems() else 0


if __name__ == "__main__":
    raise SystemExit(main())
