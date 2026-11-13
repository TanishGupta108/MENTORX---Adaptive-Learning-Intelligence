"""Geography seed (app/tutor/seed_geo.py) on a synthetic fixture, plus checks of the committed
map assets. The real Slepemapy data is never committed; tests/fixtures/geo_mini is hand-made."""

from __future__ import annotations

import json
import math
import re
from itertools import combinations
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import Subject
from app.tutor import engine
from app.tutor.models import Item, ItemSkill, Resource, Skill
from app.tutor.seed_geo import (
    MAP_WIDTH,
    MIN_ANCHOR_GAP,
    NEVER_ASKED,
    build_catalog,
    item_id,
    seed_geography,
    skill_id,
)

BACKEND = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures" / "geo_mini"
GEOMETRY = FIX / "geometry"
ARTIFACTS = FIX / "artifacts"
PLACES = FIX / "place.csv"
SHIPPED_MAPS = ("europe", "africa", "samerica", "namerica", "oceania", "us")
SOUTH_ASIA = {"in", "pk", "cn", "np", "bt", "bd", "mm", "lk", "af"}
DISPUTED_IDS = {6, 16}  # xk, pristina in the fixture
DISPUTED_NAMES = {"Kosovo", "Pristina"}


@pytest.fixture(scope="module")
def cat():
    return build_catalog(PLACES, ARTIFACTS, GEOMETRY)


def _geometry() -> dict:
    return json.loads((GEOMETRY / "geometry_europe.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- pure catalog


def test_ids_follow_the_formula(cat):
    assert skill_id("europe", 1) == 1_000_101 and skill_id("us", 7) == 1_000_607
    assert item_id(12, "europe", 0) == 100_001_202 and item_id(12, "us", 1) == 100_001_213
    assert {s["id"] for s in cat.skills} == {1_000_101, 1_000_102}
    assert {s["code"] for s in cat.skills} == {"GEO.EU.COUNTRY", "GEO.EU.CITY"}
    askable = {1, 2, 3, 4, 5, 7, 8, 11, 12, 13, 14, 15, 17}
    expected = {item_id(p, "europe", d) for p in askable for d in (0, 1)}
    assert {i["id"] for i in cat.items} == expected
    for i in cat.items:
        assert i["skill_id"] == (1_000_101 if (i["id"] // 100) % 1_000_000 < 10 else 1_000_102)
        assert i["n_skills"] == 1 and i["answer_type"] == "multiple_choice"


def test_disputed_places_are_never_asked_nor_offered(cat):
    geo = _geometry()
    disputed_d = {geo["xk"]["d"]}
    disputed_anchor = {tuple(geo["xk"]["anchor"]), tuple(geo["pristina"]["anchor"])}
    for i in cat.items:
        assert (i["id"] - 100_000_000) // 100 not in DISPUTED_IDS
        texts = [o["html"] for o in i["options"]] + [i["body_html"]]
        assert not any(n in t for n in DISPUTED_NAMES for t in texts), i
        for r in i["media"]["regions"]:
            assert r["d"] not in disputed_d or r["d"] == ""
            assert tuple(r["anchor"]) not in disputed_anchor, i["id"]
    assert {"xk", "eh", "xs", "fk", "pristina", "laayoune", "bir_lehlou", "hargeysa"} <= NEVER_ASKED


def test_four_options_exactly_one_correct(cat):
    for i in cat.items:
        ids = [o["id"] for o in i["options"]]
        assert ids == sorted(ids) and set(ids) == {"A", "B", "C", "D"}, i["id"]
        assert len(i["answer_key"]) == 1 and i["answer_key"][0] in ids
        assert i["exclusion_reason"] is None
        names = [o["html"] for o in i["options"]]
        assert len(set(names)) == 4
        if i["id"] % 2 == 1:  # locate_place: options are the letters on the map
            assert names == ids
    # the display-name override is used, and the key points at the asked place
    q = next(i for i in cat.items if i["id"] == item_id(2, "europe", 0))
    key = q["answer_key"][0]
    assert next(o["html"] for o in q["options"] if o["id"] == key) == "Federal Republic of Germany"
    loc = next(i for i in cat.items if i["id"] == item_id(2, "europe", 1))
    assert "Federal Republic of Germany" in loc["body_html"]


def test_media_carries_no_place_codes_or_answer(cat):
    geo = _geometry()
    codes = set(geo)
    names = {"France", "Germany", "Italy", "Spain", "Poland", "Sweden", "Belgium", "Paris"}
    for i in cat.items:
        m = i["media"]
        assert set(m) == {"kind", "map", "regions"} and m["kind"] == "map" and m["map"] == "europe"
        blob = json.dumps(m)
        for r in m["regions"]:
            assert set(r) == {"label", "d", "anchor", "shape"}
            assert r["shape"] in ("area", "line", "point")
        # no place code or name anywhere in the media (as a JSON string value)
        strings = set(re.findall(r'"([^"]*)"', blob))
        assert not strings & codes and not strings & names, i["id"]
        labels = [r["label"] for r in m["regions"]]
        if i["id"] % 2 == 0:  # name_place: one unlabelled region (the asked place)
            assert labels == [None]
            asked = next(c for c, g in geo.items() if g["anchor"] == m["regions"][0]["anchor"])
            assert asked not in NEVER_ASKED
        else:  # locate_place: four lettered regions, in letter order (no option->code mapping)
            assert labels == ["A", "B", "C", "D"]


def test_locate_place_anchors_are_far_apart(cat):
    gap = MIN_ANCHOR_GAP * MAP_WIDTH
    belgium_with_france = 0
    for i in cat.items:
        if i["id"] % 2 == 0:
            continue
        anchors = [r["anchor"] for r in i["media"]["regions"]]
        for a, b in combinations(anchors, 2):
            assert math.dist(a, b) >= gap, i["id"]
        if [100, 300] in anchors and [130, 290] in anchors:
            belgium_with_france += 1
    assert belgium_with_france == 0


# ---------------------------------------------------------------- committed assets


def test_committed_maps_are_the_whitelist_without_south_asia_or_disputed_places():
    geo_dir = BACKEND / "app" / "tutor" / "seeddata" / "geography"
    maps_dir = BACKEND.parent / "frontend" / "public" / "maps"
    assert sorted(p.stem for p in maps_dir.glob("*.json")) == sorted(SHIPPED_MAPS)
    assert sorted(
        p.stem.removeprefix("geometry_") for p in geo_dir.glob("geometry_*.json")
    ) == sorted(SHIPPED_MAPS)
    for m in SHIPPED_MAPS:
        base = json.loads((maps_dir / f"{m}.json").read_text(encoding="utf-8"))
        assert set(base) == {"viewBox", "land", "notice"}
        assert base["viewBox"].split()[:3] == ["0", "0", "1000"]
        assert all(re.fullmatch(r"[MLZ0-9.,\-]+", d) for d in base["land"])  # outlines only
        geometry = json.loads((geo_dir / f"geometry_{m}.json").read_text(encoding="utf-8"))
        assert not set(geometry) & (SOUTH_ASIA | NEVER_ASKED), m
    for lic in (maps_dir / "LICENSE.txt", geo_dir / "LICENSE.txt"):
        text = lic.read_text(encoding="utf-8")
        assert "MIT License" in text and "Open Database License" in text
        assert "do not show official international boundaries" in text


def test_shipped_model_artifacts_match_the_skill_rules():
    art = BACKEND / "model_artifacts" / "geography"
    meta = json.loads((art / "kt_meta.json").read_text(encoding="utf-8"))
    m = meta["models"]["dkt_q"]
    assert m["parity_max_abs_diff"] <= 1e-5
    assert m["test_metrics"]["AUC"] > meta["baseline"]["test_metrics"]["AUC"]
    assert meta["skill_ids"] == [s["id"] for s in meta["skills"]]
    for s in meta["skills"]:
        assert s["map"] in SHIPPED_MAPS
        assert len(s["places"]) >= 6 and s["dataset_answers"] >= 1000


# ---------------------------------------------------------------- database


def _rows(db, subject_code: str) -> dict:
    sid = db.scalar(select(Subject.id).where(Subject.code == subject_code))
    skills = db.scalars(select(Skill).where(Skill.subject_id == sid).order_by(Skill.id)).all()
    items = db.scalars(select(Item).where(Item.subject_id == sid).order_by(Item.id)).all()
    skill_ids = [s.id for s in skills]
    links = db.execute(
        select(ItemSkill.item_id, ItemSkill.skill_id)
        .where(ItemSkill.skill_id.in_(skill_ids))
        .order_by(ItemSkill.item_id)
    ).all()
    res = db.scalars(
        select(Resource).where(Resource.skill_id.in_(skill_ids)).order_by(Resource.id)
    ).all()
    cols = ("code", "name", "n_items", "is_available", "model_supported", "description")
    icols = (
        "skill_id",
        "body_html",
        "options",
        "answer_key",
        "difficulty",
        "media",
        "exclusion_reason",
    )
    return {
        "skills": [(s.id, *(getattr(s, c) for c in cols)) for s in skills],
        "items": [
            (i.id, *(json.dumps(getattr(i, c), sort_keys=True) for c in icols)) for i in items
        ],
        "links": [tuple(r) for r in links],
        "resources": [(r.id, r.seed_key, r.title, r.content_md) for r in res],
    }


def test_seed_is_idempotent_and_leaves_maths_alone(db, tmp_path):
    from app.tutor.seed import seed_math
    from tests.tutor.conftest import make_dataset

    make_dataset(tmp_path / "math")
    seed_math(db, tmp_path / "math", tmp_path / "math" / "artifacts")
    math_before = _rows(db, "MATH")

    summary = seed_geography(db, FIX, ARTIFACTS, GEOMETRY)
    assert summary["skills"] == 2 and summary["items"] == 26 and summary["usable_items"] == 26
    assert summary["available_skills"] == 2
    geo = db.scalar(select(Subject).where(Subject.code == "GEO"))
    assert geo.is_active
    assert db.scalar(select(Subject.is_active).where(Subject.code == "MATH"))
    first = _rows(db, "GEO")
    assert len(first["links"]) == 26
    assert summary["resources"] == len(first["resources"]) == 2  # real notes for both codes
    assert all(r[1].startswith("notes-geo-") for r in first["resources"])

    seed_geography(db, FIX, ARTIFACTS, GEOMETRY)
    assert _rows(db, "GEO") == first  # second run changes nothing
    assert _rows(db, "MATH") == math_before  # Maths untouched by the Geography seed

    seed_math(db, tmp_path / "math", tmp_path / "math" / "artifacts")
    assert _rows(db, "GEO") == first  # and a Maths reseed leaves Geography intact
    assert db.scalar(select(Subject.is_active).where(Subject.code == "GEO"))


def test_served_question_has_no_key(db):
    seed_geography(db, FIX, ARTIFACTS, GEOMETRY)
    item = db.get(Item, item_id(1, "europe", 1))
    public = engine.public_item(db, item)
    blob = json.dumps(public)
    assert "answer_key" not in public and "France" in public["body_html"]
    if "media" in public:  # added by the multi-subject API
        assert public["media"] == item.media
    assert '"fr"' not in blob and "Kosovo" not in blob
    # the id formula contains the place id (public data maps it to the answer): never sent
    assert public["item_id"] != item.id
    assert (public["item_id"] - 100_000_000) // 100 != 1
    assert engine.is_current(db, item.id, public["item_id"])
