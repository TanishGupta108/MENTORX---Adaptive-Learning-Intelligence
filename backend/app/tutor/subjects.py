"""The v2/v3 tutor's subjects: which ones exist, their credits and per-subject behaviour.

A subject is visible to students only when its `subjects` row is active (its seed ran).
Content rows (skills, items) carry `subject_id`; every "for the student's subject" read is
scoped to the student's CURRENT subject (`StudentProfile.subject_id`).
"""

from __future__ import annotations

V2_SUBJECTS = ("MATH", "GEO")  # seeding one of these never hides the other

MAP_NOTICE = "Maps are simplified for practice and do not show official international boundaries."

META: dict[str, dict] = {
    "MATH": {
        "grades": True,
        "mixed": True,
        "core_min_items": 20,  # a skill joins the placement check with >= this many questions
        "attribution": "Mathematics questions: FoundationalASSIST (ASSISTments), CC BY-NC 4.0.",
        "notice": None,
    },
    "GEO": {
        "grades": False,
        "mixed": False,
        "core_min_items": 12,  # >= 6 places x 2 question formats
        "attribution": (
            "Geography practice data © Adaptive Learning group, Masaryk University "
            "(slepemapy.cz), Open Database License 1.0. Papoušek, Pelánek & Stanislav (2016), "
            "Adaptive Geography Practice Data Set, Journal of Learning Analytics 3(2). "
            "Map outlines: adaptive-learning/geography, MIT licence, © 2013 Vít Stanislav."
        ),
        "notice": MAP_NOTICE,
        "opaque_ids": True,  # item ids contain the place id (see engine.public_id)
    },
}


def meta(code: str | None) -> dict:
    return META.get(
        code or "",
        {"grades": False, "mixed": False, "core_min_items": 20, "attribution": "", "notice": None},
    )
