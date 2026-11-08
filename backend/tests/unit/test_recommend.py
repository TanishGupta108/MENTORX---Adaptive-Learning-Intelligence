"""FR-PATH-01..03, 06 and FR-REV-01/02: the recommendation rules, without a database."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.mastery import ConceptState
from app.services.recommend import Rules, build_path, revision_due, target_difficulty

NOW = datetime(2026, 11, 8, tzinfo=UTC)
RULES = Rules()


def concept(i, name):
    return SimpleNamespace(id=i, code=f"c.{name.lower()}", name=name, topo_order=i)


def state(c, p, attempted=True, peak=None, last=None):
    return ConceptState(
        concept=c,
        p=p,
        peak=peak if peak is not None else (p if attempted else None),
        n_attempts=3 if attempted else 0,
        last_attempt_at=last,
    )


A, B, C, D, E, F, G = (concept(i, n) for i, n in enumerate("ABCDEFG", start=1))


def path(states, prereqs=None):
    return build_path({s.concept.id: s for s in states}, prereqs or {}, RULES, NOW)


@pytest.mark.parametrize(
    ("p", "level"), [(0.0, 1), (0.39, 1), (0.4, 2), (0.69, 2), (0.7, 3), (1.0, 3)]
)
def test_target_difficulty_follows_mastery_bands(p, level):
    assert target_difficulty(p) == level


def test_weak_concept_with_prerequisites_in_place_is_recommended():
    recs = path([state(A, 0.9), state(B, 0.3)], {B.id: [A.id]})
    assert [(r.concept_id, r.reason) for r in recs] == [(B.id, "weak")]
    assert recs[0].target_difficulty == 1
    assert "30%" in recs[0].explanation and "prerequisites are in place" in recs[0].explanation


def test_missing_prerequisite_is_recommended_instead():
    """FR-PATH-02, and the FR-PATH-06 example wording."""
    recs = path([state(A, 0.45), state(B, 0.3)], {B.id: [A.id]})
    assert [(r.concept_id, r.reason) for r in recs] == [(A.id, "prerequisite")]
    assert recs[0].explanation == "B builds on A, which you're at 45% on. Strengthen it first."


def test_walks_down_a_chain_of_missing_prerequisites():
    # C needs B needs A; all weak -> only the root of the gap, A, is recommended
    recs = path([state(A, 0.4), state(B, 0.3), state(C, 0.2)], {B.id: [A.id], C.id: [B.id]})
    assert [(r.concept_id, r.reason) for r in recs] == [(A.id, "prerequisite")]


def test_picks_the_weakest_missing_prerequisite():
    recs = path([state(A, 0.5), state(B, 0.3), state(C, 0.2)], {C.id: [A.id, B.id]})
    reasons = {r.concept_id: r.reason for r in recs}
    assert reasons[B.id] == "prerequisite"  # weakest gap for C
    assert reasons[A.id] == "weak"  # A itself is weak with no prerequisites
    assert C.id not in reasons


def test_never_practised_prerequisite_is_not_in_place_whatever_the_estimate():
    recs = path([state(A, 0.75, attempted=False), state(B, 0.3)], {B.id: [A.id]})
    assert [(r.concept_id, r.reason) for r in recs] == [(A.id, "prerequisite")]
    assert "haven't practised yet" in recs[0].explanation


def test_unpractised_concept_with_prerequisites_in_place_is_new():
    recs = path([state(A, 0.9), state(B, 0.62, attempted=False)], {B.id: [A.id]})
    assert [(r.concept_id, r.reason) for r in recs] == [(B.id, "new")]


def test_revision_comes_first_and_is_not_duplicated():
    last = NOW - timedelta(days=12)
    recs = path([state(A, 0.2), state(B, 0.5, peak=0.9, last=last)])
    assert [(r.concept_id, r.reason) for r in recs] == [(B.id, "revision"), (A.id, "weak")]
    assert "90%" in recs[0].explanation and "50%" in recs[0].explanation
    assert "12 days ago" in recs[0].explanation


def test_ranking_and_length():
    states = [
        state(A, 0.5),  # weak
        state(B, 0.3),  # weak, weaker
        state(C, 0.4, attempted=False),  # new
        state(D, 0.55, peak=0.85),  # revision
        state(E, 0.45),  # prerequisite of F
        state(F, 0.2),
        state(G, 0.1),  # weak, weakest
    ]
    recs = path(states, {F.id: [E.id]})
    assert len(recs) == 5
    assert [r.reason for r in recs] == ["revision", "prerequisite", "weak", "weak", "weak"]
    assert [r.concept_id for r in recs] == [D.id, E.id, G.id, B.id, A.id]  # C (new) cut


def test_fills_with_not_yet_mastered_after_everything_else():
    recs = path([state(A, 0.95), state(B, 0.7), state(C, 0.65), state(D, 0.5, attempted=False)])
    assert [(r.concept_id, r.reason) for r in recs] == [
        (D.id, "new"),
        (C.id, "weak"),
        (B.id, "weak"),
    ]
    assert "80% counts as mastered" in recs[1].explanation


def test_everything_mastered_gives_an_empty_path():
    assert path([state(A, 0.9), state(B, 0.85)], {B.id: [A.id]}) == []


def test_revision_due_rule_and_order():
    s = [
        state(A, 0.55, peak=0.82),  # drop 0.27
        state(B, 0.40, peak=0.95),  # drop 0.55
        state(C, 0.59, peak=0.79),  # never reached the peak threshold
        state(D, 0.61, peak=0.95),  # still above the floor
        state(E, 0.30, attempted=False),
    ]
    assert [x.concept.id for x in revision_due(s, RULES)] == [B.id, A.id]
