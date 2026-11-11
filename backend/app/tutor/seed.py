"""Load Mathematics content from the FoundationalASSIST CSVs into the database (idempotent).

The raw CSVs are never committed (CC BY-NC 4.0, gated download). Point the seed command at
the folder that holds Problems.csv and Skills.csv. Difficulty comes from the exported model
artifacts (question_stats.json: training students only), so it matches what the model saw.

Every dataset question is stored. Questions the app cannot serve reliably keep an
`exclusion_reason` (multi-skill, unsupported answer type, image, several blanks, ...), so the
admin page can show exactly why something is unavailable.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Subject
from app.tutor import answers
from app.tutor.html import count_blanks, has_unrenderable, sanitize
from app.tutor.models import Item, ItemSkill, Resource, Skill, SkillPrerequisite

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).parent / "seeddata"
SUBJECT_CODE = "MATH"
SUBJECT_NAME = "Mathematics"
SUBJECT_DESCRIPTION = (
    "Grade 3-8 mathematics aligned to the Common Core State Standards: ratios, the number "
    "system, expressions and equations, geometry, statistics and more. Questions come from the "
    "FoundationalASSIST dataset (Illustrative Mathematics content in ASSISTments)."
)
DOMAINS = {
    "OA": "Operations & Algebraic Thinking",
    "NBT": "Number & Operations in Base Ten",
    "NF": "Fractions",
    "MD": "Measurement & Data",
    "G": "Geometry",
    "RP": "Ratios & Proportional Relationships",
    "NS": "The Number System",
    "EE": "Expressions & Equations",
    "SP": "Statistics & Probability",
    "F": "Functions",
}
TYPE_MAP = {
    "Numeric": "numeric",
    "Multiple Choice": "multiple_choice",
    "Check All That Apply": "check_all",
}
MIN_RATED_ATTEMPTS = 10  # a question's difficulty needs at least this many training answers
MIN_ITEMS_FOR_SKILL = 5  # a skill is offered only with enough usable questions


def difficulty_level(rate: float | None, attempts: int) -> str:
    """Historical difficulty from TRAINING students' first-attempt success rate."""
    if rate is None or attempts < MIN_RATED_ATTEMPTS:
        return "unrated"
    if rate >= 0.75:
        return "easy"
    if rate >= 0.45:
        return "medium"
    return "hard"


def parse_code(code: str) -> tuple[int | None, str]:
    parts = code.split(".")
    grade = int(parts[0]) if parts and parts[0].isdigit() else None
    domain = parts[1] if len(parts) > 1 else "OTHER"
    return grade, domain


def standard_url(code: str) -> str | None:
    """Single-standard page on thecorestandards.org, e.g. 7.EE.B.4a -> /Math/Content/7/EE/B/4/a/."""
    parts = code.split(".")
    if len(parts) != 4 or not parts[0].isdigit():
        return None
    num, letter = parts[3][:-1], parts[3][-1]
    tail = f"{num}/{letter}" if parts[3][-1].isalpha() and num.isdigit() else parts[3]
    return f"https://www.thecorestandards.org/Math/Content/{parts[0]}/{parts[1]}/{parts[2]}/{tail}/"


@dataclass
class ItemRow:
    item: dict
    skills: list[int]


def build_items(problems: pd.DataFrame, skills: pd.DataFrame, stats: dict) -> list[ItemRow]:
    by_problem = skills.groupby("problem_id")["skill_id"].apply(
        lambda s: sorted(set(int(x) for x in s))
    )
    rows: list[ItemRow] = []
    for _, p in problems.drop_duplicates("problem_id").iterrows():
        pid = int(p["problem_id"])
        sk = by_problem.get(pid, [])
        if not sk:
            continue
        body_raw = str(p["Problem Body"])
        kind = TYPE_MAP.get(str(p["Answer Types"]).strip(), "other")
        options: list[dict] = []
        key: list[str] | None = []
        reason = None
        if len(sk) > 1:
            reason = "multi_skill"
        elif kind == "other":
            reason = f"unsupported_answer_type: {str(p['Answer Types']).strip()}"[:80]
        elif has_unrenderable(body_raw) or has_unrenderable(str(p["Multiple Choice Options"])):
            reason = "image_or_unrenderable_math"
        if kind == "numeric":
            if reason is None and count_blanks(body_raw) != 1:
                reason = "not_one_answer_blank"
            key = (
                answers.numeric_key(p["Fill-in Answers"])
                if pd.notna(p["Fill-in Answers"])
                else None
            )
        elif kind in ("multiple_choice", "check_all"):
            raw_opts = (
                answers.split_options(p["Multiple Choice Options"])
                if pd.notna(p["Multiple Choice Options"])
                else []
            )
            raw_ans = (
                answers.split_options(p["Multiple Choice Answers"])
                if pd.notna(p["Multiple Choice Answers"])
                else []
            )
            options = [{"id": str(i), "html": sanitize(o)} for i, o in enumerate(raw_opts)]
            key = answers.choice_key(raw_opts, raw_ans) if len(raw_opts) >= 2 else None
            if kind == "multiple_choice" and key and len(key) != 1:
                key = None
        if reason is None and not key:
            reason = "missing_or_unparseable_answer_key"
        st = stats.get(str(pid), {})
        rate, n = st.get("success_rate"), int(st.get("attempts", 0))
        rows.append(
            ItemRow(
                item={
                    "id": pid,
                    "skill_id": sk[0],
                    "body_html": sanitize(body_raw),
                    "answer_type": kind,
                    "options": options,
                    "answer_key": key or [],
                    "difficulty": difficulty_level(rate, n),
                    "success_rate": rate,
                    "train_attempts": n,
                    "n_skills": len(sk),
                    "problem_set": str(p["Problem Set Id"])[:40],
                    "exclusion_reason": reason,
                },
                skills=sk,
            )
        )
    return rows


def _subject(db: Session) -> Subject:
    subject = db.scalar(select(Subject).where(Subject.code == SUBJECT_CODE))
    if subject is None:
        subject = Subject(code=SUBJECT_CODE, name=SUBJECT_NAME, description=SUBJECT_DESCRIPTION)
        db.add(subject)
        db.flush()
    subject.name, subject.description, subject.is_active = SUBJECT_NAME, SUBJECT_DESCRIPTION, True
    return subject


def seed_math(
    db: Session, data_dir: Path, artifact_dir: Path, deactivate_other_subjects: bool = True
) -> dict:
    problems = pd.read_csv(data_dir / "Problems.csv")
    skills_df = pd.read_csv(data_dir / "Skills.csv")
    stats = json.loads((artifact_dir / "question_stats.json").read_text())["questions"]
    meta = json.loads((artifact_dir / "kt_meta.json").read_text())
    model_skills = set(meta["skill_ids"])

    subject = _subject(db)
    if deactivate_other_subjects:  # v1 scope: Mathematics only
        for s in db.scalars(select(Subject).where(Subject.id != subject.id)):
            s.is_active = False

    # skills (descriptions edited by admins are preserved)
    names = skills_df.drop_duplicates("skill_id").set_index("skill_id").sort_index()
    # Several dataset skill IDs share one standard code (different content units). Number
    # them so students can tell them apart: "Solve Problems Involving Percents (set 2 of 3)".
    code_ids = names.groupby("node_code").groups
    existing = {s.id: s for s in db.scalars(select(Skill))}
    for sid, row in names.iterrows():
        code = str(row["node_code"]).strip()
        grade, domain = parse_code(code)
        name = str(row["node_name"]).strip()
        siblings = sorted(int(x) for x in code_ids[row["node_code"]])
        if len(siblings) > 1:
            name = f"{name} (set {siblings.index(int(sid)) + 1} of {len(siblings)})"
        s = existing.get(int(sid)) or Skill(id=int(sid), subject_id=subject.id, description="")
        s.subject_id, s.code, s.name = subject.id, code, name
        s.grade, s.domain_code, s.domain_name = grade, domain, DOMAINS.get(domain, domain)
        s.standard_url = standard_url(code)
        s.model_supported = int(sid) in model_skills
        db.add(s)
    db.flush()

    # items and the full question-skill mapping (admin availability toggles are preserved)
    rows = build_items(problems, skills_df, stats)
    current = {i.id: i for i in db.scalars(select(Item))}
    db.execute(delete(ItemSkill))
    for r in rows:
        item = current.get(r.item["id"]) or Item(id=r.item["id"], is_active=True)
        for k, v in r.item.items():
            setattr(item, k, v)
        item.subject_id = subject.id
        db.add(item)
    db.flush()
    db.add_all(ItemSkill(item_id=r.item["id"], skill_id=s) for r in rows for s in r.skills)

    usable: dict[int, int] = {}
    for r in rows:
        if r.item["exclusion_reason"] is None:
            usable[r.item["skill_id"]] = usable.get(r.item["skill_id"], 0) + 1
    for s in db.scalars(select(Skill)):
        s.n_items = usable.get(s.id, 0)
        s.is_available = s.n_items >= MIN_ITEMS_FOR_SKILL and s.model_supported

    prereqs = seed_prerequisites(db)
    resources = seed_resources(db)
    db.commit()
    summary = {
        "skills": len(names),
        "available_skills": sum(1 for v in usable.values() if v >= MIN_ITEMS_FOR_SKILL),
        "items": len(rows),
        "usable_items": sum(usable.values()),
        "prerequisites": prereqs,
        "resources": resources,
    }
    logger.info("math seed: %s", summary)
    return summary


def _skills_by_code(db: Session) -> dict[str, list[Skill]]:
    out: dict[str, list[Skill]] = {}
    for s in db.scalars(select(Skill)):
        out.setdefault(s.code, []).append(s)
    return out


def seed_prerequisites(db: Session) -> int:
    """Curated links from seeddata/prerequisites.yaml (Common Core progressions). Codes that
    map to several skill IDs link all of them. Admin-added links are kept."""
    spec = yaml.safe_load((SEED_DIR / "prerequisites.yaml").read_text(encoding="utf-8"))
    by_code = _skills_by_code(db)
    have = {(p.skill_id, p.prerequisite_id) for p in db.scalars(select(SkillPrerequisite))}
    added = 0
    for link in spec["links"]:
        for s in by_code.get(link["skill"], []):
            for p in by_code.get(link["requires"], []):
                if s.id != p.id and (s.id, p.id) not in have:
                    db.add(
                        SkillPrerequisite(
                            skill_id=s.id, prerequisite_id=p.id, source=spec["source"]
                        )
                    )
                    have.add((s.id, p.id))
                    added += 1
    return len(have)


def seed_resources(db: Session) -> int:
    """Original notes/worked examples (seeddata/resources.yaml) and one genuine Common Core
    standard link per skill. Upserted by seed_key, so admin-created resources are untouched."""
    spec = yaml.safe_load((SEED_DIR / "resources.yaml").read_text(encoding="utf-8"))
    by_code = _skills_by_code(db)
    existing = {
        r.seed_key: r for r in db.scalars(select(Resource).where(Resource.seed_key.is_not(None)))
    }

    def upsert(key: str, **fields) -> None:
        r = existing.get(key) or Resource(seed_key=key)
        for k, v in fields.items():
            setattr(r, k, v)
        db.add(r)

    for s in db.scalars(select(Skill).where(Skill.standard_url.is_not(None))):
        upsert(
            f"standard:{s.id}",
            skill_id=s.id,
            kind="standard",
            title=f"Common Core standard {s.code}",
            description="The official wording of this standard, with its examples.",
            url=s.standard_url,
            content_md=None,
            minutes=3,
            source_label="thecorestandards.org",
            is_original=False,
            position=90,
        )
    for res in spec["resources"]:
        for s in by_code.get(res["skill"], []):
            upsert(
                f"{res['key']}:{s.id}",
                skill_id=s.id,
                kind=res["kind"],
                title=res["title"],
                description=res.get("description", ""),
                url=None,
                content_md=res["content"].strip(),
                minutes=res.get("minutes", 5),
                source_label="MENTORX original demo content",
                is_original=True,
                position=res.get("position", 10),
            )
    db.flush()
    return db.query(Resource).count()
