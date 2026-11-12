"""Smoke test a running MENTORX deployment end to end (standard library only).

Usage:
    python scripts/smoke.py https://mentorx-adaptive-learning-intellige.vercel.app  # via /api
    python scripts/smoke.py https://mentorx-backend-uco2.onrender.com
    python scripts/smoke.py http://localhost:8000

Creates a throwaway account, then tests whichever product is live:
- v2 (Mathematics seeded): onboarding, one adaptive-diagnostic question (no answer key leaked),
  the diagnosis, the dashboard, the model and the AI tutor status;
- v1 (Machine Learning subject): enrol, one diagnostic question, dashboard, learning path.
Then it DELETES the account. Exits 1 on the first failure.
Over plain HTTP the refresh-cookie check is skipped (the cookie is Secure in production).
"""

from __future__ import annotations

import http.cookiejar
import json
import secrets
import sys
import time
import urllib.error
import urllib.request


class Smoke:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/") + "/api/v1"
        self.https = base.startswith("https://")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.token: str | None = None

    def call(self, method: str, path: str, body: dict | None = None, expect: int = 200):
        req = urllib.request.Request(
            self.base + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "mentorx-smoke/1.0",
                **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
            },
        )
        start = time.perf_counter()
        try:
            with self.opener.open(req, timeout=60) as r:
                status, raw, headers = r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            status, raw, headers = e.code, e.read(), e.headers
        ms = (time.perf_counter() - start) * 1000
        if status != expect:
            raise AssertionError(f"{method} {path}: expected {expect}, got {status}: {raw[:300]!r}")
        print(f"  ok  {method:6} {path:45} {status} {ms:6.0f} ms")
        return (json.loads(raw) if raw else None), headers


def v2_is_live(s: Smoke) -> bool:
    """True if the v2 Mathematics tutor is deployed and seeded (GET /api/v2/subject = 200)."""
    v1 = s.base
    s.base = v1.removesuffix("/v1") + "/v2"
    try:
        s.call("GET", "/subject")
        return True
    except AssertionError as e:
        print(f"  --  v2 Mathematics not live ({str(e)[:80]}); testing v1")
        return False
    finally:
        s.base = v1


def smoke_v2(s: Smoke) -> None:
    v1 = s.base
    s.base = v1.removesuffix("/v1") + "/v2"
    try:
        sub, _ = s.call("GET", "/subject")
        assert sub["n_skills"] >= 10 and sub["n_questions"] >= 100, "maths content too small"
        assert sub["model"]["available"], "knowledge-tracing model not loaded"
        print(
            f"  {sub['n_skills']} skills, {sub['n_questions']} questions",
            f"model {sub['model']['name']}",
        )
        s.call(
            "POST", "/onboarding", {"goal_type": "assess_overall", "goal_kind": "weekly_practice"}
        )
        a, _ = s.call("POST", "/assessments", {"kind": "diagnostic"}, 201)
        q, _ = s.call("GET", f"/assessments/{a['id']}/next")
        assert "answer_key" not in q and q["selection"]["how"], "question leaked or unexplained"
        body = {"item_id": q["item_id"]}
        if q["answer_type"] == "multiple_choice":
            body["choice"] = q["options"][0]["id"]
        elif q["answer_type"] == "check_all":
            body["choices"] = [q["options"][0]["id"]]
        else:
            body["value"] = "1"
        r, _ = s.call("POST", f"/assessments/{a['id']}/answer", body)
        assert r["correct_answer"], "no feedback after answering"
        dash, _ = s.call("GET", "/dashboard")
        assert dash["streak"]["today"] == 1, dash["streak"]
        ai, _ = s.call("GET", "/ai/status")
        print(f"  AI tutor enabled: {ai['enabled']}")
    finally:
        s.base = v1


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    s = Smoke(sys.argv[1])
    email = f"smoke-{secrets.token_hex(6)}@example.com"
    print(f"Smoke test against {s.base} as {email}")
    try:
        body, headers = s.call("GET", "/health")
        assert body == {"status": "ok"}
        assert headers.get("X-Content-Type-Options") == "nosniff", "security headers missing"
        if s.https:
            assert headers.get("Strict-Transport-Security"), "HSTS missing over HTTPS"
        s.call("GET", "/health/ready")

        body, _ = s.call(
            "POST",
            "/auth/register",
            {
                "email": email,
                "password": secrets.token_urlsafe(16),
                "full_name": "Smoke Test",
                "privacy_accepted": True,
            },
            expect=201,
        )
        s.token = body["access_token"]
        if s.https:
            body, _ = s.call("POST", "/auth/refresh")  # proves the refresh cookie round-trips
            s.token = body["access_token"]
        else:
            print("  --  POST   /auth/refresh: skipped over plain HTTP (Secure cookie)")

        s.call("GET", "/me")
        if v2_is_live(s):
            smoke_v2(s)
            print("PASSED (v2)")
            return 0
        subjects, _ = s.call("GET", "/subjects")
        assert any(x["code"] == "ML" and x["concept_count"] > 0 for x in subjects), subjects
        s.call("POST", "/subjects/ML/enroll")
        session, _ = s.call("POST", "/sessions", {"subject": "ML", "type": "diagnostic"}, 201)
        q, _ = s.call("POST", f"/sessions/{session['id']}/next")
        assert "correct_key" not in q, "answer key leaked to the client"
        s.call(
            "POST",
            f"/sessions/{session['id']}/answer",
            {"question_id": q["question_id"], "selected_key": None},
        )
        dash, _ = s.call("GET", "/dashboard?subject=ML")
        assert dash["questions_answered"] == 1, dash
        path, _ = s.call("GET", "/learning-path?subject=ML")
        assert path["model_version"], "no active model version"
        print(f"  model in use: {path['model_version']}")

        streak, _ = s.call("GET", "/engagement/streak")
        assert streak["daily_goal"] >= 1 and streak["current_streak"] >= 0, streak
        weekly, _ = s.call("GET", "/engagement/weekly?subject=ML")
        assert weekly["questions"] == 1, weekly
        study, _ = s.call("GET", "/pilot/status?subject=ML")
        assert "group" not in study and "pretest" in study, study  # the arm is never revealed
        # Deleted with the throwaway account below.
        s.call("POST", "/feedback", {"rating": 5, "category": "other", "page": "/smoke"}, 201)
    except (AssertionError, KeyError, urllib.error.URLError) as e:
        print(f"FAILED: {e}")
        return 1
    finally:
        if s.token:
            try:
                s.call("DELETE", "/me", {"confirm_email": email}, expect=204)
            except Exception as e:  # noqa: BLE001 - report, don't mask the main result
                print(f"WARNING: couldn't delete the smoke-test account {email}: {e}")
    print("PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
