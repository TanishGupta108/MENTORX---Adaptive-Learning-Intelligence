"""FR-CONT-01/02, FR-DASH-02 (concept graph)."""

from app.content.question_bank import QUESTION_BANK_DIR, load_question_bank
from tests.conftest import auth, register


def test_list_subjects_shows_concept_count_and_enrolment(client, seeded):
    h = auth(register(client))
    subjects = client.get("/api/v1/subjects", headers=h).json()
    assert subjects == [
        {
            "code": "ML",
            "name": "Machine Learning",
            "description": subjects[0]["description"],
            "concept_count": 19,
            "enrolled": False,
        }
    ]
    client.post("/api/v1/subjects/ML/enroll", headers=h)
    assert client.get("/api/v1/subjects", headers=h).json()[0]["enrolled"] is True


def test_enroll_is_idempotent_and_case_insensitive(client, seeded):
    h = auth(register(client))
    for code in ("ML", "ml"):
        r = client.post(f"/api/v1/subjects/{code}/enroll", headers=h)
        assert r.status_code == 200
        assert r.json() == {"subject": "ML", "enrolled": True, "diagnostic_completed": False}
    assert client.get("/api/v1/me", headers=h).json()["enrolled_subjects"] == ["ML"]


def test_unknown_subject_is_404_with_error_shape(client, seeded):
    h = auth(register(client))
    r = client.post("/api/v1/subjects/NOPE/enroll", headers=h)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "subject_not_found"


def test_concepts_follow_prerequisite_order_and_match_the_yaml(client, seeded):
    h = auth(register(client))
    concepts = client.get("/api/v1/subjects/ML/concepts", headers=h).json()
    bank = load_question_bank(QUESTION_BANK_DIR / "machine_learning")
    expected = {c.code: sorted(c.prerequisites) for c in bank.concepts}
    assert {c["code"]: c["prerequisites"] for c in concepts} == expected
    position = {c["code"]: i for i, c in enumerate(concepts)}
    for c in concepts:
        for pre in c["prerequisites"]:
            assert position[pre] < position[c["code"]]
    # no answers yet, so no mastery estimate: null, never a made-up number (FR-DASH-08)
    assert all(c["mastery"] is None and c["n_attempts"] == 0 for c in concepts)


def test_subjects_require_login(client, seeded):
    assert client.get("/api/v1/subjects").status_code == 401
