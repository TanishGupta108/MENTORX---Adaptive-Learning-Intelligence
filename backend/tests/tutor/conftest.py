"""Fixtures for the tutor: a small SYNTHETIC dataset in the FoundationalASSIST CSV format.

The real dataset is licensed (CC BY-NC 4.0, gated) and never committed, so tests generate
their own questions. Skill IDs are real ones the exported model knows, so the real model
artifacts are exercised end to end.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from tests.conftest import auth, register

ARTIFACTS = Path(__file__).resolve().parents[2] / "model_artifacts" / "foundationalassist"
# (skill_id, code, name): real dataset skills, so the model supports them
SKILLS = [
    (129, "6.RP.A.3a", "Create Tables to Compare Equivalent Ratios"),
    (130, "6.RP.A.3b", "Solve Unit Rate Problems"),
    (166, "6.EE.B.7", "Write & Solve 1-Step Equations"),
    (135, "6.NS.A.1", "Interpret & Compute using Division of Fractions"),
    (217, "7.EE.B.4a", "Solve 2-Step Equations"),
    (198, "7.RP.A.3", "Use Proportional Relationships to Solve Ratio & Percent Problems"),
    (219, "7.G.A.1", "Solve Scale Drawing Problems"),
    (222, "7.G.B.4", "Solve Problems Involving Area & Circumference of Circles"),
    (139, "6.NS.B.3", "Add, Subtract, Multiply & Divide Multi-Digit Decimals"),
    (156, "6.EE.A.1", "Write & Evaluate Numerical Expressions with Exponents"),
]
PER_SKILL = 24
RATES = [0.85, 0.6, 0.3]  # easy, medium, hard (training success rates)


def make_dataset(folder: Path) -> dict[int, dict]:
    """Write Problems.csv / Skills.csv. Returns {problem_id: {"answer": ..., "type": ...}}."""
    problems, skills, stats, keys = [], [], {}, {}
    pid = 900000
    for sid, code, name in SKILLS:
        for k in range(PER_SKILL):
            pid += 1
            a, b = k + 2, sid % 7 + 1
            kind = ["Numeric", "Multiple Choice", "Check All That Apply"][k % 3]
            row = {
                "Problem Set Id": f"PS{sid}",
                "Problem Part": 1,
                "Problem Type": "x",
                "Answer Types": kind,
                "Problem Body": f'<p onclick="evil()">What is {a} + {b}?</p><p><ast-r type="text" marker="1"></ast-r></p>',
                "Fill-in Options": None,
                "Fill-in Answers": None,
                "Multiple Choice Options": None,
                "Multiple Choice Answers": None,
                "problem_id": pid,
            }
            if kind == "Numeric":
                row["Fill-in Answers"] = f"{a + b:,}" if a + b >= 1000 else str(a + b)
                keys[pid] = {"type": "numeric", "answer": str(a + b), "wrong": str(a + b + 1)}
            elif kind == "Multiple Choice":
                row["Problem Body"] = f"<p>Pick {a + b}.</p>"
                row["Multiple Choice Options"] = f"{a + b - 1} || {a + b} || {a + b + 1}"
                row["Multiple Choice Answers"] = str(a + b)
                keys[pid] = {"type": "multiple_choice", "answer": "1", "wrong": "0"}
            else:
                row["Problem Body"] = "<p>Select the even numbers.</p>"
                row["Multiple Choice Options"] = "2 || 3 || 4 || 5"
                row["Multiple Choice Answers"] = "2 || 4"
                keys[pid] = {"type": "check_all", "answer": ["0", "2"], "wrong": ["0"]}
            problems.append(row)
            skills.append(
                {"problem_id": pid, "skill_id": sid, "node_code": code, "node_name": name}
            )
            stats[str(pid)] = {
                "attempts": 50,
                "success_rate": RATES[k % 3],
                "smoothed_rate": RATES[k % 3],
            }
    # one multi-skill and one image question: stored but excluded
    pid += 1
    problems.append({**problems[0], "problem_id": pid})
    skills += [
        {"problem_id": pid, "skill_id": 129, "node_code": "6.RP.A.3a", "node_name": SKILLS[0][2]},
        {"problem_id": pid, "skill_id": 130, "node_code": "6.RP.A.3b", "node_name": SKILLS[1][2]},
    ]
    pid += 1
    problems.append(
        {
            **problems[0],
            "problem_id": pid,
            "Problem Body": '<p>Look <img src="/x.png"></p><ast-r></ast-r>',
        }
    )
    skills.append(
        {"problem_id": pid, "skill_id": 129, "node_code": "6.RP.A.3a", "node_name": SKILLS[0][2]}
    )
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(problems).to_csv(folder / "Problems.csv", index=False)
    pd.DataFrame(skills).to_csv(folder / "Skills.csv", index=False)
    art = folder / "artifacts"
    art.mkdir(exist_ok=True)
    shutil.copy(ARTIFACTS / "kt_meta.json", art / "kt_meta.json")
    (art / "question_stats.json").write_text(
        json.dumps({"global_success_rate": 0.6, "questions": stats})
    )
    return keys


@pytest.fixture
def math_keys(db, tmp_path):
    from app.tutor.seed import seed_math

    keys = make_dataset(tmp_path / "data")
    seed_math(db, tmp_path / "data", tmp_path / "data" / "artifacts")
    return keys


@pytest.fixture
def learner(client, math_keys):
    h = auth(register(client))
    r = client.post(
        "/api/v2/onboarding",
        json={"goal_type": "assess_overall", "goal_kind": "weekly_practice"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    return h


def answer_body(keys: dict, item: dict, correct: bool) -> dict:
    k = keys[item["item_id"]]
    v = k["answer"] if correct else k["wrong"]
    field = {"numeric": "value", "multiple_choice": "choice", "check_all": "choices"}[k["type"]]
    return {"item_id": item["item_id"], field: v}
