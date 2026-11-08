"""NFR-PERF-01 load test: N concurrent students taking diagnostics and practice sessions.

Usage (against a server whose registration limit allows N sign-ups from one IP):
    REGISTRATIONS_PER_HOUR=1000 uvicorn app.main:app --port 8000      # in one terminal
    python scripts/loadtest.py http://127.0.0.1:8000 --users 50 --questions 20

Each simulated student arrives during the ramp-up period, registers, enrols, then repeatedly
asks for the next question and answers it (with think time between requests). Reports
p50/p95/max latency per endpoint and the errors. The requirement: p95 <= 300 ms for next
question and submit answer. Accounts are deleted at the end.
(On Windows use 127.0.0.1, not localhost: localhost tries IPv6 first and adds ~2 s.)
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import random
import secrets
import statistics
import time
from collections import defaultdict

import httpx

LAT: dict[str, list[float]] = defaultdict(list)
ERRORS: dict[str, int] = defaultdict(int)


async def timed(client: httpx.AsyncClient, name: str, method: str, url: str, **kw):
    start = time.perf_counter()
    try:
        r = await client.request(method, url, **kw)
    except httpx.HTTPError as e:
        ERRORS[f"{name} {type(e).__name__}"] += 1
        raise
    LAT[name].append((time.perf_counter() - start) * 1000)
    if r.status_code >= 400:
        ERRORS[f"{name} {r.status_code}"] += 1
    return r


async def student(base: str, n_questions: int, think: float, delay: float, rng) -> None:
    await asyncio.sleep(delay)  # users arrive over the ramp-up period, not all at once
    with contextlib.suppress(httpx.HTTPError):  # already counted in ERRORS
        await _student(base, n_questions, think, rng)


async def _student(base: str, n_questions: int, think: float, rng: random.Random) -> None:
    async with httpx.AsyncClient(base_url=f"{base}/api/v1", timeout=30) as c:
        email = f"load-{secrets.token_hex(6)}@example.com"
        r = await timed(
            c,
            "register",
            "POST",
            "/auth/register",
            json={
                "email": email,
                "password": "correct horse 1",
                "full_name": "Load Test",
                "privacy_accepted": True,
            },
        )
        if r.status_code != 201:
            return
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        await timed(c, "enroll", "POST", "/subjects/ML/enroll")
        sid = None
        for i in range(n_questions):
            if sid is None:
                body = {"subject": "ML", "type": "diagnostic" if i == 0 else "practice"}
                r = await timed(c, "start session", "POST", "/sessions", json=body)
                sid = r.json()["id"]
            r = await timed(c, "next question", "POST", f"/sessions/{sid}/next")
            if r.status_code != 200:
                sid = None
                continue
            q = r.json()
            await asyncio.sleep(think * rng.uniform(0.5, 1.5))
            r = await timed(
                c,
                "submit answer",
                "POST",
                f"/sessions/{sid}/answer",
                json={"question_id": q["question_id"], "selected_key": rng.choice("ABCD")},
            )
            if r.status_code == 200 and r.json()["session_complete"]:
                sid = None
            await asyncio.sleep(think * rng.uniform(0.5, 1.5))
        await timed(c, "dashboard", "GET", "/dashboard?subject=ML")
        await timed(c, "delete account", "DELETE", "/me", json={"confirm_email": email})


def pctl(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("base")
    p.add_argument("--users", type=int, default=50)
    p.add_argument("--questions", type=int, default=20)
    p.add_argument("--think", type=float, default=1.0, help="mean seconds between requests")
    p.add_argument("--ramp", type=float, default=10.0, help="seconds over which users arrive")
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    rng = random.Random(a.seed)
    start = time.perf_counter()
    await asyncio.gather(
        *(
            student(a.base, a.questions, a.think, a.ramp * i / a.users, random.Random(rng.random()))
            for i in range(a.users)
        )
    )
    wall = time.perf_counter() - start
    print(
        f"{a.users} users arriving over {a.ramp:.0f} s, {a.questions} questions each, "
        f"~{a.think:.1f} s think time, {wall:.0f} s wall time\n"
    )
    print(f"{'endpoint':16} {'n':>5} {'p50 ms':>8} {'p95 ms':>8} {'max ms':>8}")
    for name, xs in LAT.items():
        p50, p95 = statistics.median(xs), pctl(xs, 0.95)
        print(f"{name:16} {len(xs):5d} {p50:8.0f} {p95:8.0f} {max(xs):8.0f}")
    print(f"\nerrors: {dict(ERRORS) or 'none'}")
    ok = all(pctl(LAT[k], 0.95) <= 300 for k in ("next question", "submit answer") if LAT[k])
    print("NFR-PERF-01 (p95 <= 300 ms):", "PASS" if ok and not ERRORS else "FAIL")


if __name__ == "__main__":
    asyncio.run(main())
