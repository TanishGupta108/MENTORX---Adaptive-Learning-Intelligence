"""FR-ENG-01/03: current and longest streak from the days a goal was met."""

from datetime import date, timedelta

import pytest

from app.services.engagement import streaks

T = date(2026, 11, 9)


def days(*offsets: int) -> set[date]:
    return {T - timedelta(days=o) for o in offsets}


@pytest.mark.parametrize(
    ("met", "current", "longest"),
    [
        (set(), 0, 0),
        (days(0), 1, 1),
        (days(0, 1, 2), 3, 3),
        (days(1, 2), 2, 2),  # today not done yet: yesterday's streak is still alive
        (days(2, 3), 0, 2),  # missed yesterday: streak broken
        (days(0, 2, 3, 4, 5), 1, 4),  # longest is in the past
        (days(0, 1, 5, 6, 7), 2, 3),
        (days(10), 0, 1),
    ],
)
def test_streaks(met, current, longest):
    assert streaks(met, T) == (current, longest)


def test_month_and_year_boundaries_are_consecutive():
    met = {date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 2)}
    assert streaks(met, date(2026, 1, 2)) == (3, 3)
