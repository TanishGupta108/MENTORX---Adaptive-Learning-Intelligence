import random
from collections import Counter

import pytest

from app.services.selection import select_index


def test_adaptive_picks_only_among_k_closest_to_target():
    preds = [0.95, 0.66, 0.30, 0.64, 0.70, 0.10]
    # distances to 0.65: .30 .01 .35 .01 .05 .55 -> closest three: idx 1, 3, 4
    picks = Counter(select_index(preds, "adaptive", 0.65, 3, random.Random(s)) for s in range(300))
    assert set(picks) == {1, 3, 4}


def test_top_k_one_is_deterministic():
    assert select_index([0.2, 0.6, 0.9], None, 0.65, 1, random.Random(0)) == 1


def test_control_group_ignores_predictions():
    preds = [0.65, 0.01, 0.02, 0.03]
    picks = Counter(select_index(preds, "control", 0.65, 1, random.Random(s)) for s in range(400))
    assert set(picks) == {0, 1, 2, 3}


def test_empty_candidates_raise():
    with pytest.raises(ValueError):
        select_index([], None, 0.65, 3, random.Random(0))
