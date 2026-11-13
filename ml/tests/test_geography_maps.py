"""Geometry helpers of scripts/build_geography_maps.py (no SVGs needed)."""

import importlib.util
import re
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "build_geography_maps",
    Path(__file__).resolve().parents[1] / "scripts" / "build_geography_maps.py",
)
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)


def test_map_with_south_asian_code_is_rejected(tmp_path):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 500">'
        '<g id="state"><path data-code="in" d="M0,0L10,0L10,10Z"/></g></svg>'
    )
    p = tmp_path / "bad.svg"
    p.write_text(svg, encoding="utf-8")
    with pytest.raises(AssertionError, match="South Asian"):
        B.build_map(p)


def test_disputed_places_get_no_geometry_and_base_map_has_no_codes(tmp_path):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 500">'
        '<g id="bg"><path d="M0,0L900,0L900,400Z"/></g>'
        '<g id="state"><path data-code="fr" d="M0,0L100,0L100,100L0,100Z"/>'
        '<path data-code="xk" d="M200,0L300,0L300,100L200,100Z"/></g>'
        '<g id="city"><circle data-code="Pristina" data-state-code="xk" cx="250" cy="50" r="8"/>'
        '<circle data-code="Paris" data-state-code="fr" cx="50" cy="50" r="8"/></g></svg>'
    )
    p = tmp_path / "m.svg"
    p.write_text(svg, encoding="utf-8")
    base, geometry, report = B.build_map(p)
    assert set(geometry) == {"fr", "paris"}
    assert geometry["paris"] == {
        "d": "",
        "anchor": [50, 50],
        "bbox": [50, 50, 50, 50],
        "shape": "point",
    }
    assert len(base["land"]) == 3  # bg + both states drawn as plain land (xk included, unlabelled)
    assert all(re.fullmatch(r"[MLZ0-9.,\-]+", d) for d in base["land"])  # outlines only, no codes
    assert sorted(report["skipped"]) == ["pristina", "xk"]


def test_anchor_of_a_place_running_off_the_map_is_inside_the_view_box(tmp_path):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 500">'
        '<g id="state"><path data-code="ru" d="M800,100L3000,-2000L3000,450L800,450Z"/></g>'
        '<g id="river"><path data-code="volga" d="M900,200L950,250L2000,900"/></g></svg>'
    )
    p = tmp_path / "m.svg"
    p.write_text(svg, encoding="utf-8")
    _, geometry, _ = B.build_map(p)
    for g in geometry.values():
        x, y = g["anchor"]
        assert 0 <= x <= 1000 and 0 <= y <= 500, g
        x0, y0, x1, y1 = g["bbox"]
        assert 0 <= x0 <= x1 <= 1000 and 0 <= y0 <= y1 <= 500
