"""The student's own day: streaks, daily goals and the AI daily limit use the user's timezone
(`users.timezone`, default Asia/Kolkata), not UTC, so the day turns over at local midnight."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FALLBACK_TZ = "Asia/Kolkata"


def tz_of(user) -> tzinfo:
    name = getattr(user, "timezone", None) or FALLBACK_TZ
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        try:
            return ZoneInfo(FALLBACK_TZ)
        except ZoneInfoNotFoundError:  # no tz database at all (tzdata missing): use UTC
            return UTC


def local_date(ts: datetime, tz: tzinfo) -> date:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(tz).date()


def today(user, now: datetime | None = None) -> date:
    return local_date(now or datetime.now(UTC), tz_of(user))


def day_start(user, day: date | None = None) -> datetime:
    """The UTC instant when the user's local `day` (default: today) began."""
    tz = tz_of(user)
    day = day or today(user)
    return datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC)


def days_ago_start(user, days: int) -> datetime:
    return day_start(user, today(user) - timedelta(days=days))
