# MENTORX Testing Report

**Version:** M12, 2026-11-09 · **System under test:** commit history up to M11 + M12 fixes ·
**Environments:** local (Windows 11, Python 3.14, PostgreSQL), CI (GitHub Actions, Ubuntu,
Python 3.12, PostgreSQL 17), production (Vercel + Render free plan + Render PostgreSQL).

Every number in this report comes from a command that was actually run. The command is given next
to each result so it can be reproduced.

## 1. Strategy

| Level | What it checks | Tools | Where |
|---|---|---|---|
| Unit | Pure logic: recommendation rules, question selection, streaks, security helpers, question-bank rules | pytest | `backend/tests/unit` |
| Integration | Database + model together: seeding, migrations vs models, knowledge tracing behaviour, the pilot study flow | pytest on a real PostgreSQL database | `backend/tests/integration` |
| API | Every endpoint through HTTP: auth, authorisation, validation, error shape, business rules | pytest + FastAPI TestClient | `backend/tests/api` |
| ML | Data cleaning, leakage guards, feature equality between training and serving, metrics, BKT | pytest | `ml/tests` |
| Frontend | Components and pages against a mocked API: routing, empty states, quiz flow, dashboard, feedback, study flow | Vitest + Testing Library | `frontend/src/**/*.test.tsx` |
| System (end to end) | A real deployment: sign-up → enrol → answer → dashboard → path → streak → study status → feedback → delete | `backend/scripts/smoke.py` | CI (Docker image) and production |
| Performance | Latency under concurrent students | `backend/scripts/loadtest.py` | local and production |
| Security | Headers, rate limits, production config, dependency audit | pytest, npm audit | §5 |

Tests run on a **real PostgreSQL database**, not SQLite or mocks, so constraints, cascades,
time zones and migrations are tested as they behave in production. Each test starts from an empty,
migrated database.

**Continuous integration:** every push runs four jobs, and deployment happens only after all pass:
1. **backend:** lint, format check, migrations, tests with coverage;
2. **ml:** lint, format check, tests;
3. **frontend:** type check, tests, production build;
4. **docker:** builds the production image, starts it in production mode against PostgreSQL, and
   runs the end-to-end smoke test against it.

## 2. Results

| Suite | Tests | Result | Command |
|---|---:|---|---|
| Backend: unit | 50 | all pass | `cd backend && pytest tests/unit` |
| Backend: integration | 26 | all pass | `pytest tests/integration` |
| Backend: API | 76 | all pass | `pytest tests/api` |
| ML package | 48 | all pass | `cd ml && pytest` |
| Frontend | 28 | all pass | `cd frontend && npm test` |
| **Total automated** | **228** | **all pass** | |
| End-to-end smoke test, production | 17 steps | pass | `python scripts/smoke.py https://mentorx-adaptive-learning-intellige.vercel.app` |

**Coverage:** backend **97%** of statements (2,518 statements, 67 not covered;
`pytest --cov=app`). NFR-MAINT-01 requires ≥ 80%. ML and frontend coverage were not measured
(the coverage plugins aren't installed). Their tests target the riskiest code instead: leakage,
train/serve equality, the quiz flow.

### Backend tests per area

| File | Tests | Requirements covered |
|---|---:|---|
| `api/test_auth.py` | 11 | FR-AUTH: registration, login, refresh rotation, logout, rate limits |
| `api/test_me.py` | 7 | FR-AUTH-08..11: profile, export, deletion |
| `api/test_subjects.py` | 5 | FR-CONT: subjects, concepts, enrolment |
| `api/test_sessions.py` | 13 | FR-DIAG, FR-QUIZ: sessions, serving, answering, no answer-key leak |
| `api/test_learning.py` | 8 | FR-PATH, FR-REV |
| `api/test_dashboard.py` | 6 | FR-DASH, local days, question flags |
| `api/test_engagement.py` | 14 | FR-ENG-01..05, FR-PILOT-03 |
| `api/test_hardening.py` | 9 | NFR-SEC: headers, HSTS, rate limits, production config, request IDs, JSON logs |
| `api/test_health.py` | 3 | health and readiness |
| `integration/test_knowledge.py` | 7 | FR-KT: model fallbacks, mastery decay, monotone envelope, difficulty cache |
| `integration/test_pilot.py` | 13 | FR-PILOT-01/02/04/05, FR-DASH-09, FR-QUIZ-10 |
| `integration/test_seed.py` | 5 | FR-CONT-05/06: versioning, retiring, drafts |
| `integration/test_migrations.py` | 1 | NFR-MAINT-03: models equal migrations |
| `unit/test_question_bank.py` | 14 | content standard: coverage, letter balance, forms |
| `unit/test_recommend.py` | 17 | learning-path and revision rules on synthetic students |
| `unit/test_selection.py` | 4 | target-probability selection, control group randomness |
| `unit/test_security.py` | 6 | hashing, tokens |
| `unit/test_streaks.py` | 9 | streak arithmetic, month and year boundaries |

## 3. Performance (NFR-PERF-01)

**Requirement:** `next question` and `submit answer` p95 ≤ 300 ms with 50 concurrent users,
excluding cold starts.

**Method:** `loadtest.py` simulates N students arriving over 10 s. Each registers, enrols, then
repeatedly asks for the next question and answers it (20 questions, about 1 s think time).
Local runs use one uvicorn process (as deployed) on the development laptop, with the registration
limit raised for the test.

### Local results (one server process)

| Concurrent students | next question p50 / p95 | submit answer p50 / p95 | Errors | NFR-PERF-01 |
|---:|---|---|---:|---|
| 1 | 35 / 41 ms | 43 / 52 ms | 0 | pass |
| 10 | 40 / 79 ms | 52 / 169 ms | 0 | **pass** |
| 25 | 76 / 363 ms | 93 / 400 ms | 0 | fail |
| 50, before the M12 fix | 3,329 / 6,889 ms | 3,767 / 8,225 ms | 6 | fail |
| 50, after the M12 fix | 464 / 1,273 ms | 512 / 1,571 ms | 0 | **fail** |

**Finding and fix.** Profiling showed that each request re-aggregated every student's answers
to compute question difficulty. That cost grows with the size of the answers table. M12 caches
the all-student totals for 60 s and subtracts the requesting student's own answers from the same
snapshot (`app/ml/knowledge.py`). The numbers served are identical, which is tested in
`test_cached_difficulty_matches_a_fresh_computation`. Only other students' newest answers can
arrive up to 60 s late. At 50 students, p95 fell about 5× and the errors disappeared.

**Verdict: NFR-PERF-01 is not met at 50 concurrent users.** It is met at 10. Each request is
cheap (about 40 ms), but a single Python process can't serve 50 students who each send a request
about every second. The remaining cost is dominated by recomputing the student's mastery state for
the learning path on every "next question".

### Production (Render free plan)

| Students | next question p50 / p95 | submit answer p50 / p95 | Note |
|---:|---|---|---|
| 2 | 205 / 390 ms | 234 / 421 ms | measured before the M12 fix, from India, through Vercel to Render Singapore |

Even a trivial call (enrol) took about 136 ms here, so roughly 130 ms of each request is network
and proxy. The free instance has a fraction of one CPU.

**Recommendations before the pilot:**
1. Move the API to a paid instance with more CPU, e.g. Render Starter.
2. Cache each student's mastery state between their own answers. This is the next hotspot.
3. With a shared store (Redis) for the rate limiters, run several worker processes.

### Other performance requirements

| ID | Result | Evidence |
|---|---|---|
| NFR-PERF-03: initial JS ≤ 250 KB gzipped | **met**: 104 KB gzipped (CSS 5.6 KB) | `npm run build` |
| NFR-PERF-02: dashboard LCP ≤ 2.5 s on a mid-range phone | **not measured** | needs a Lighthouse run in a browser |
| NFR-ML-03: 50 candidates ≤ 50 ms | **met** during model selection | [ml-report.md](../ml-report.md) |

## 4. Defects found and fixed during testing

| # | Found by | Defect | Fix |
|---|---|---|---|
| 1 | Production use (M9) | Sign-up failed: the frontend's `/api` rewrite pointed at a guessed host belonging to another Render user | Rewrite set to the real service; "never guess the host" added to the deployment guide; smoke test runs through the real frontend |
| 2 | Load test (M12) | Latency grew with the answers table; errors at 50 users | Difficulty statistics cache (§3) |
| 3 | npm audit (M12) | `react-router` 7.9 had high-severity advisories (open redirect, XSS) | Updated to 7.18.5: 0 production vulnerabilities |
| 4 | Serving analysis (M7) | Mastery could rise with time alone, so concepts flipped in and out of revision | Monotone envelope (D-10), with a test |
| 5 | CI (M10) | A test assumed draft questions exist; it failed once all were reviewed | Test made independent of the bank's review state |
| 6 | Code review (M9) | A client-supplied `X-Request-ID` was written to logs unchecked (log injection) | Only short plain IDs are echoed; others are replaced |
| 7 | AI answer-key check (M10) | nn-014 was answered correctly even with the bias or the ReLU forgotten | Input changed so each mistake gives a different wrong option |

## 5. Non-functional requirements: status

| ID | Status | Evidence / gap |
|---|---|---|
| PERF-01 | **Partly met** | Met at 10 concurrent users, not at 50 (§3) |
| PERF-02 | Not measured | Lighthouse not run |
| PERF-03 | Met | 104 KB gzipped |
| SEC-01 | Met | HTTPS on Vercel and Render; HSTS tested |
| SEC-02 | Met | Pydantic on every input; SQLAlchemy only; validation tests |
| SEC-03 | Met | Another student gets 404 on your sessions (tested); flags only for questions you were shown; export and deletion act on the caller only |
| SEC-04 | Partly met | Secrets only in environment variables, `.env` git-ignored; no automated secret scan in CI |
| SEC-05 | Met | CORS restricted to the configured origin; same-origin rewrite |
| SEC-06 | Partly met | `npm audit`: 0 production vulnerabilities after the fix; 1 moderate in the test tool `vitest` (dev only, needs a major upgrade); not yet automated in CI; Python audit not run |
| PRIV-01 | Met | Only name, email, learning data; no third-party scripts (CSP forbids them) |
| PRIV-02 | Met | Exports use an HMAC pseudonym; tested to contain no email or name |
| PRIV-03 | Met | Deletion cascades; tested including goal days and feedback |
| REL-01 | Partly met | Attempts are append-only; mastery recomputes from attempts on read, but there is no one-shot rebuild command |
| REL-02 | **Not met on the free plan** | Render's free database has no automated backups, so upgrade before the pilot |
| REL-03 | Met | JSON error with request ID; tested |
| USE-01 | Not measured | 5-user usability test pending |
| USE-02 | Pending pilot | SUS collected at the end of the pilot |
| USE-03 | Partly met | Responsive layout, 44 px targets by design; no automated viewport test |
| ACC-01 | Partly met | Labels, roles and keyboard support are covered by the frontend tests' accessible queries; no axe-core audit |
| MAINT-01 | Met | 97% backend coverage; CI must pass before deploy |
| MAINT-02 | Met | Routers delegate to services |
| MAINT-03 | Met | Model/migration equality test |
| ML-01 | Met | [ml-report.md](../ml-report.md) §8 |
| ML-02 | Met | Leakage tests in `ml/tests/test_features.py` |
| ML-04 | Met | ECE 0.004 |
| PORT-01 | Met | README local setup; `docker-compose.yml` for PostgreSQL |
| OBS-01 | Partly met | Every request is logged with request ID and latency (JSON in production); user ID not included |

## 6. Not yet tested (honest gaps)

- **The pilot itself:** learning gain, SUS, live model calibration on real students. The tooling
  is built and tested; the results need the study to run.
- **Browser-level checks:** Lighthouse performance, axe accessibility audit, real-device viewport
  tests.
- **Usability test** with 5 new users (NFR-USE-01).
- **Load at the production scale after the M12 fix**, on a paid instance.
