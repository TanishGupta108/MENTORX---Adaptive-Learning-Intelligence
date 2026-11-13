"""Load the Geography subject (map skills, Slepemapy.cz data) into the database (idempotent).

Sources (the raw data is never committed):
- place.csv from the Slepemapy.cz 2015-05-21 data set (Open Database License 1.0): place names.
- model_artifacts/geography/: kt_meta.json (the shipped skills and their places, chosen by
  ml/scripts/train_geography_kt.py) and question_stats.json (training students' success rates,
  and the places students most often confused with each one).
- seeddata/geography/geometry_<map>.json: server-only outlines of every askable place
  (ml/scripts/build_geography_maps.py), and names.yaml (display-name fixes).

Every Geography question is single-skill multiple choice with four options:
- name_place   "What is the name of the highlighted country?"  1 region, options = place names
- locate_place "Where is France? Choose the letter on the map."  4 regions lettered A-D, options A-D
Distractors are the same-skill places students confused most often with the asked place,
falling back to random same-skill places (fixed seed). For locate_place every two lettered
places are at least 6 % of the map width apart, so the letters never overlap.

No leaks: `media` carries only outlines (`d`), anchors, shapes and option letters, never a place
code, name or id, and the regions of a locate question are listed in letter order. The key is
an option id in `items.answer_key` (server only). Disputed places are never asked or offered.
This seed never touches Mathematics rows.
"""

from __future__ import annotations

import csv
import html
import json
import logging
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Subject
from app.tutor.html import sanitize
from app.tutor.models import Item, ItemSkill, Resource, Skill
from app.tutor.seed import MIN_ITEMS_FOR_SKILL, difficulty_level

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).parent / "seeddata"
GEOMETRY_DIR = SEED_DIR / "geography"
RESOURCES_FILE = SEED_DIR / "resources_geography.yaml"
SUBJECT_CODE = "GEO"
SUBJECT_NAME = "Geography"
SUBJECT_DESCRIPTION = (
    "Map skills: find and name the countries, cities, rivers, mountains and islands of Europe, "
    "Africa, the Americas, Oceania and the United States. Practice data from slepemapy.cz "
    "(Masaryk University)."
)
GEO_MAPS = {"europe": 1, "africa": 2, "samerica": 3, "namerica": 4, "oceania": 5, "us": 6}
MAP_NAMES = {
    "europe": "Europe",
    "africa": "Africa",
    "samerica": "South America",
    "namerica": "North America",
    "oceania": "Oceania",
    "us": "the United States",
}
# Disputed status: never asked and never offered as an option (still drawn as plain land).
NEVER_ASKED = frozenset(
    {"xk", "eh", "xs", "fk", "ps", "tw", "pristina", "bir_lehlou", "laayoune", "hargeysa"}
)
TERRITORY_MAPS = {"samerica", "namerica", "oceania"}  # their "countries" include territories
NOUN = {
    1: "country",
    2: "city",
    5: "river",
    6: "lake",
    7: "US state",
    8: "mountain area",
    9: "island",
}
PLURAL = {
    1: "countries",
    2: "cities",
    5: "rivers",
    6: "lakes",
    7: "states",
    8: "mountains",
    9: "islands",
}
LETTERS = ("A", "B", "C", "D")
MIN_PLACES_FOR_SKILL = 6
MIN_ANCHOR_GAP = 0.06  # locate_place: lettered places at least 6 % of the map width apart
MAP_WIDTH = 1000.0  # every shipped map's viewBox is 1000 wide (asserted by build_geography_maps.py)
MAP_SHORT = {
    "europe": "EU",
    "africa": "AF",
    "samerica": "SA",
    "namerica": "NA",
    "oceania": "OC",
    "us": "US",
}
TYPE_CODE = {
    1: "COUNTRY",
    2: "CITY",
    5: "RIVER",
    6: "LAKE",
    7: "STATE",
    8: "MOUNTAINS",
    9: "ISLAND",
}
SEED = 42


def item_id(place_id: int, map_code: str, direction: int) -> int:
    """direction 0 = name_place, 1 = locate_place."""
    return 100_000_000 + int(place_id) * 100 + GEO_MAPS[map_code] * 2 + int(direction)


def skill_id(map_code: str, type_id: int) -> int:
    return 1_000_000 + GEO_MAPS[map_code] * 100 + int(type_id)


def noun(map_code: str, type_id: int) -> str:
    if type_id == 1 and map_code in TERRITORY_MAPS:
        return "country or territory"
    return NOUN[type_id]


# Country names that take "the" in English; plural ones take "are".
THE_COUNTRIES = (
    "United ",
    "Republic of",
    "Democratic Republic",
    "Central African Republic",
    "Dominican Republic",
    "Czech Republic",
    "Netherlands",
    "Bahamas",
    "Solomon Islands",
    "Gambia",
)
PLURAL_COUNTRIES = ("Bahamas", "Solomon Islands")


def where(name: str, type_id: int) -> str:
    """'Where is France?', 'Where is the river Niger?', 'Where are the Alps?'."""
    if type_id == 5:  # rivers: "the river Niger", never confused with the country Niger
        return f"Where is the river {name}?"
    the = type_id in (6, 8) or (type_id == 1 and name.startswith(THE_COUNTRIES))
    plural_name = (type_id == 8 and name.endswith("s")) or name in PLURAL_COUNTRIES
    return f"Where {'are' if plural_name else 'is'} {'the ' if the else ''}{name}?"


def plural(map_code: str, type_id: int) -> str:
    if type_id == 1 and map_code in TERRITORY_MAPS:
        return "countries and territories"
    return PLURAL[type_id]


def skill_name(map_code: str, type_id: int) -> str:
    if map_code == "us":
        return "US states" if type_id == 7 else "Cities of the United States"
    return f"{plural(map_code, type_id).capitalize()} of {MAP_NAMES[map_code]}"


@dataclass
class Catalog:
    skills: list[dict] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    skipped_skills: list[str] = field(default_factory=list)


def _places(place_csv: Path) -> dict[int, dict]:
    with open(place_csv, encoding="utf-8", newline="") as fh:
        return {
            int(r["id"]): {
                "code": r["code"].strip().lower(),
                "name": r["name"].strip(),
                "type": int(r["type"]),
            }
            for r in csv.DictReader(fh, delimiter=";")
        }


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_catalog(
    place_csv: Path, artifact_dir: Path, geometry_dir: Path = GEOMETRY_DIR
) -> Catalog:
    """Skills and items from the data files only (pure: no database)."""
    places = _places(place_csv)
    meta = _load_json(artifact_dir / "kt_meta.json")
    stats = _load_json(artifact_dir / "question_stats.json")["questions"]
    names_file = geometry_dir / "names.yaml"
    names = yaml.safe_load(names_file.read_text(encoding="utf-8")) if names_file.exists() else {}
    fixed, by_map = names.get("names") or {}, names.get("by_map") or {}
    model_skills = {int(s) for s in meta.get("skill_ids", [])}
    cat = Catalog()
    geometries: dict[str, dict] = {}
    for spec in meta["skills"]:
        m, t = spec["map"], int(spec["place_type_id"])
        if m not in GEO_MAPS or t not in NOUN:
            cat.skipped_skills.append(spec.get("code", f"{m}:{t}"))
            continue
        if m not in geometries:
            geometries[m] = _load_json(geometry_dir / f"geometry_{m}.json")
        geo = geometries[m]
        pool = []
        for pid in spec["places"]:
            p = places.get(int(pid))
            if p and p["type"] == t and p["code"] in geo and p["code"] not in NEVER_ASKED:
                pool.append(int(pid))
        if len(pool) < MIN_PLACES_FOR_SKILL:
            cat.skipped_skills.append(spec.get("code", f"{m}:{t}"))
            continue

        def name(pid: int, m: str = m) -> str:
            code = places[pid]["code"]
            return (by_map.get(m) or {}).get(code) or fixed.get(code) or places[pid]["name"]

        sid = skill_id(m, t)
        cat.skills.append(
            {
                "id": sid,
                "code": f"GEO.{MAP_SHORT[m]}.{TYPE_CODE[t]}",
                "name": skill_name(m, t),
                "description": f"Find and name the {plural(m, t)} on a map of {MAP_NAMES[m]}.",
                "domain_code": MAP_SHORT[m],
                "domain_name": MAP_NAMES[m].removeprefix("the "),
                "model_supported": sid in model_skills,
                "map": m,
                "places": len(pool),
            }
        )
        for pid in pool:
            for direction in (0, 1):
                cat.items.append(_item(pid, m, t, direction, sid, pool, geo, stats, name, places))
    return cat


def _item(pid, m, t, direction, sid, pool, geo, stats, name, places) -> dict:
    iid = item_id(pid, m, direction)
    st = stats.get(str(iid), {})
    pool_set = set(pool)
    confused = [int(p) for p in st.get("confusions", []) if int(p) in pool_set and int(p) != pid]
    rng = random.Random(SEED * 1_000_003 + iid)
    others = [p for p in pool if p != pid]
    rng.shuffle(others)
    candidates = confused + [p for p in others if p not in confused]

    def anchor(p: int) -> list[float]:
        return geo[places[p]["code"]]["anchor"]

    chosen: list[int] = []
    seen_names = {name(pid)}
    anchors = [anchor(pid)]
    for p in candidates:
        if len(chosen) == 3:
            break
        if name(p) in seen_names:
            continue
        if direction == 1 and any(
            math.dist(anchor(p), a) < MIN_ANCHOR_GAP * MAP_WIDTH for a in anchors
        ):
            continue
        chosen.append(p)
        seen_names.add(name(p))
        anchors.append(anchor(p))
    members = [pid] + chosen
    rng.shuffle(members)
    letter = {p: LETTERS[i] for i, p in enumerate(members)}

    def region(p: int, label: str | None) -> dict:
        g = geo[places[p]["code"]]
        return {"label": label, "d": g["d"], "anchor": list(g["anchor"]), "shape": g["shape"]}

    if direction == 0:
        body = f"<p>What is the name of the highlighted {noun(m, t)}?</p>"
        options = [
            {"id": letter[p], "html": sanitize(html.escape(name(p), quote=False))} for p in members
        ]
        regions = [region(pid, None)]
    else:
        body = (
            f"<p>{html.escape(where(name(pid), t), quote=False)} Choose the letter on the map.</p>"
        )
        options = [{"id": letter[p], "html": letter[p]} for p in members]
        regions = [region(p, letter[p]) for p in members]
    rate, n = st.get("success_rate"), int(st.get("attempts", 0))
    return {
        "id": iid,
        "skill_id": sid,
        "body_html": sanitize(body),
        "answer_type": "multiple_choice",
        "options": options,
        "answer_key": [letter[pid]],
        "difficulty": difficulty_level(rate, n),
        "success_rate": rate,
        "train_attempts": n,
        "n_skills": 1,
        "problem_set": f"GEO.{m}.{'name' if direction == 0 else 'locate'}"[:40],
        "exclusion_reason": None if len(chosen) == 3 else "not_enough_distinct_places",
        "media": {"kind": "map", "map": m, "regions": regions},
    }


def _subject(db: Session) -> Subject:
    subject = db.scalar(select(Subject).where(Subject.code == SUBJECT_CODE))
    if subject is None:
        subject = Subject(code=SUBJECT_CODE, name=SUBJECT_NAME, description=SUBJECT_DESCRIPTION)
        db.add(subject)
        db.flush()
    subject.name, subject.description, subject.is_active = SUBJECT_NAME, SUBJECT_DESCRIPTION, True
    return subject


def seed_geography(
    db: Session, data_dir: Path, artifact_dir: Path, geometry_dir: Path = GEOMETRY_DIR
) -> dict:
    """Upsert the GEO subject, skills, items, item-skill links and notes. Maths is untouched."""
    cat = build_catalog(Path(data_dir) / "place.csv", Path(artifact_dir), Path(geometry_dir))
    subject = _subject(db)

    skill_ids = {s["id"] for s in cat.skills}
    item_ids = {i["id"] for i in cat.items}
    clash_s = db.scalars(
        select(Skill.id).where(Skill.id.in_(skill_ids), Skill.subject_id != subject.id)
    ).all()
    clash_i = db.scalars(
        select(Item.id).where(Item.id.in_(item_ids), Item.subject_id != subject.id)
    ).all()
    if clash_s or clash_i:
        raise RuntimeError(
            f"Geography ids collide with other subjects: skills {clash_s[:5]}, items {clash_i[:5]}"
        )

    existing = {s.id: s for s in db.scalars(select(Skill).where(Skill.subject_id == subject.id))}
    for spec in cat.skills:
        s = existing.get(spec["id"]) or Skill(id=spec["id"], subject_id=subject.id, description="")
        s.subject_id, s.code, s.name = subject.id, spec["code"], spec["name"]
        s.grade, s.domain_code, s.domain_name = None, spec["domain_code"], spec["domain_name"]
        s.standard_url = None
        s.model_supported = spec["model_supported"]
        if not s.description:  # admin-edited descriptions are kept
            s.description = spec["description"]
        db.add(s)
    db.flush()

    current = {i.id: i for i in db.scalars(select(Item).where(Item.subject_id == subject.id))}
    for row in cat.items:
        item = current.get(row["id"]) or Item(id=row["id"], is_active=True)
        for k, v in row.items():
            if getattr(item, k, None) != v:
                setattr(item, k, v)
        item.subject_id = subject.id
        db.add(item)
    for iid, item in current.items():  # dropped from the catalog: kept (history), never served
        if iid not in item_ids and item.exclusion_reason != "not_in_catalog":
            item.exclusion_reason = "not_in_catalog"
    db.flush()

    geo_items = select(Item.id).where(Item.subject_id == subject.id)
    db.execute(delete(ItemSkill).where(ItemSkill.item_id.in_(geo_items)))
    db.add_all(ItemSkill(item_id=r["id"], skill_id=r["skill_id"]) for r in cat.items)

    usable: dict[int, int] = {}
    for r in cat.items:
        if r["exclusion_reason"] is None:
            usable[r["skill_id"]] = usable.get(r["skill_id"], 0) + 1
    for s in db.scalars(select(Skill).where(Skill.subject_id == subject.id)):
        s.n_items = usable.get(s.id, 0) if s.id in skill_ids else 0
        s.is_available = (
            s.id in skill_ids and s.n_items >= MIN_ITEMS_FOR_SKILL and s.model_supported
        )

    resources = seed_resources(db, subject.id)
    db.commit()
    summary = {
        "skills": len(cat.skills),
        "available_skills": sum(
            1
            for s in cat.skills
            if usable.get(s["id"], 0) >= MIN_ITEMS_FOR_SKILL and s["model_supported"]
        ),
        "items": len(cat.items),
        "usable_items": sum(usable.values()),
        "excluded_items": sum(1 for r in cat.items if r["exclusion_reason"]),
        "skipped_skills": len(cat.skipped_skills),
        "resources": resources,
    }
    logger.info("geography seed: %s", summary)
    return summary


def seed_resources(db: Session, subject_id: int, path: Path = RESOURCES_FILE) -> int:
    """One short notes resource per skill from resources_geography.yaml (upsert by seed_key,
    same key format as the Maths seed: "<key>:<skill id>"). Returns the GEO notes count."""
    if not path.exists():
        return 0
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    by_code = {s.code: s for s in db.scalars(select(Skill).where(Skill.subject_id == subject_id))}
    keys = [
        f"{r['key']}:{by_code[r['skill']].id}" for r in spec["resources"] if r["skill"] in by_code
    ]
    existing = {
        r.seed_key: r for r in db.scalars(select(Resource).where(Resource.seed_key.in_(keys)))
    }
    for res in spec["resources"]:
        s = by_code.get(res["skill"])
        if s is None:
            continue
        key = f"{res['key']}:{s.id}"
        r = existing.get(key) or Resource(seed_key=key)
        fields = {
            "skill_id": s.id,
            "kind": res["kind"],
            "title": res["title"],
            "description": res.get("description", ""),
            "url": None,
            "content_md": res["content"].strip(),
            "minutes": res.get("minutes", 3),
            "source_label": spec["source_label"],
            "is_original": True,
            "position": res.get("position", 10),
        }
        for k, v in fields.items():
            if getattr(r, k, None) != v:
                setattr(r, k, v)
        db.add(r)
    db.flush()
    return len(keys)
