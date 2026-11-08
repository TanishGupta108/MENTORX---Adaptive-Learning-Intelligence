"""Learning-path and revision rules (FR-PATH, FR-REV), as pure functions.

No database access here: the inputs are each concept's current mastery (from the ML model,
see `mastery.current`) and the prerequisite graph, so every rule is unit-testable.
The algorithm is the one in docs/design/uml.md §3.2.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.core.config import Settings
from app.services.mastery import ConceptState

REASON_RANK = {"revision": 0, "prerequisite": 1, "weak": 2, "new": 3}


@dataclass(frozen=True)
class Rules:
    met: float = 0.6  # prerequisite counts as in place (FR-PATH-02)
    mastered: float = 0.8
    revision_peak: float = 0.8  # FR-REV-01
    revision_floor: float = 0.6
    length: int = 5  # FR-PATH-01

    @classmethod
    def from_settings(cls, cfg: Settings) -> Rules:
        return cls(
            met=cfg.mastery_threshold,
            mastered=cfg.mastered_threshold,
            revision_peak=cfg.revision_peak,
            revision_floor=cfg.revision_floor,
            length=cfg.path_length,
        )


@dataclass
class Recommendation:
    concept_id: int
    reason: str
    target_difficulty: int
    mastery: float
    explanation: str


def target_difficulty(p: float) -> int:
    """FR-PATH-03: mastery band -> difficulty. <0.4 -> 1, 0.4-0.7 -> 2, >=0.7 -> 3."""
    return 1 if p < 0.4 else 2 if p < 0.7 else 3


def pct(p: float) -> str:
    return f"{round(p * 100)}%"


def is_met(s: ConceptState | None, rules: Rules) -> bool:
    """In place = practised AND estimated at or above the threshold.

    A never-practised prerequisite is not "in place", whatever the model's prior guess.
    """
    return s is not None and s.attempted and s.p >= rules.met


def revision_due(states: Sequence[ConceptState], rules: Rules) -> list[ConceptState]:
    """FR-REV-01/02: peaked at >= revision_peak, now below revision_floor; biggest drop first."""
    due = [
        s
        for s in states
        if s.attempted
        and s.peak is not None
        and s.peak >= rules.revision_peak
        and s.p < rules.revision_floor
    ]
    return sorted(due, key=lambda s: (-(s.peak - s.p), s.concept.topo_order))


def _ago(last: datetime | None, now: datetime) -> str:
    if last is None:
        return ""
    days = (now - last).days
    if days < 1:
        return " (earlier today)"
    return f" ({days} day{'s' if days != 1 else ''} ago)"


def build_path(
    states: dict[int, ConceptState],
    prereqs: dict[int, list[int]],
    rules: Rules,
    now: datetime,
) -> list[Recommendation]:
    """FR-PATH-01..03, 06: up to `rules.length` concepts, each with a reason and explanation.

    1. Revision: concepts due for revision.
    2. Every concept below `met` (or never practised), in prerequisite order:
       - prerequisites in place -> recommend it (weak if practised, new otherwise);
       - otherwise -> walk down to its weakest missing prerequisite whose own prerequisites
         are in place, and recommend that (reason = prerequisite).
    3. Rank: revision > prerequisite > weak > new, then lowest mastery, then prerequisite order.
    4. Still room: concepts that are in place but not yet mastered, weakest first.
    """
    ordered = sorted(states.values(), key=lambda s: s.concept.topo_order)
    chosen: dict[int, Recommendation] = {}

    def offer(s: ConceptState, reason: str, explanation: str) -> None:
        old = chosen.get(s.concept.id)
        if old is None or REASON_RANK[reason] < REASON_RANK[old.reason]:
            chosen[s.concept.id] = Recommendation(
                s.concept.id, reason, target_difficulty(s.p), s.p, explanation
            )

    def missing(cid: int) -> list[ConceptState]:
        return [
            states[p] for p in prereqs.get(cid, []) if p in states and not is_met(states[p], rules)
        ]

    for s in revision_due(ordered, rules):
        offer(
            s,
            "revision",
            f"You reached {pct(s.peak)} on {s.concept.name}, but it has dropped to {pct(s.p)} "
            f"since you last practised it{_ago(s.last_attempt_at, now)}. "
            "A short revision will bring it back.",
        )

    for s in ordered:
        if is_met(s, rules):
            continue
        if not missing(s.concept.id):
            if s.attempted:
                where = (
                    "its prerequisites are in place"
                    if prereqs.get(s.concept.id)
                    else "it doesn't depend on other concepts"
                )
                offer(
                    s,
                    "weak",
                    f"You're at {pct(s.p)} on {s.concept.name}, and {where}, "
                    "so it's a good next step.",
                )
            else:
                where = (
                    ", and its prerequisites are in place"
                    if prereqs.get(s.concept.id)
                    else ". It's a starting point: it doesn't depend on other concepts"
                )
                offer(s, "new", f"You haven't practised {s.concept.name} yet{where}.")
            continue
        # Walk down the prerequisite graph (a DAG, so this terminates).
        child, cur = s, s
        while gaps := missing(cur.concept.id):
            child, cur = cur, min(gaps, key=lambda g: (g.p, g.concept.topo_order))
        state = (
            f"which you're at {pct(cur.p)} on"
            if cur.attempted
            else "which you haven't practised yet"
        )
        offer(
            cur,
            "prerequisite",
            f"{child.concept.name} builds on {cur.concept.name}, {state}. Strengthen it first.",
        )

    ranked = sorted(
        chosen.values(),
        key=lambda r: (REASON_RANK[r.reason], r.mastery, states[r.concept_id].concept.topo_order),
    )[: rules.length]

    if len(ranked) < rules.length:
        taken = {r.concept_id for r in ranked}
        fill = sorted(
            (
                s
                for s in ordered
                if s.concept.id not in taken
                and is_met(s, rules)
                and s.p < rules.mastered
                and not missing(s.concept.id)
            ),
            key=lambda s: (s.p, s.concept.topo_order),
        )
        for s in fill[: rules.length - len(ranked)]:
            ranked.append(
                Recommendation(
                    s.concept.id,
                    "weak",
                    target_difficulty(s.p),
                    s.p,
                    f"You're at {pct(s.p)} on {s.concept.name}. "
                    f"Reaching {pct(rules.mastered)} counts as mastered.",
                )
            )
    return ranked
