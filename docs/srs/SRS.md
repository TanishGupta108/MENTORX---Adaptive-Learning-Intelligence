# Software Requirements Specification: MENTORX

| | |
|---|---|
| Version | 1.0 (M1) |
| Date | 2026-11-08 |
| Status | Baseline for MVP development |
| Structure | Based on IEEE 830 / ISO/IEC/IEEE 29148 |
| Related | [User stories](user-stories.md) · [Use cases](use-cases.md) · [Architecture](../design/architecture.md) · [Database](../design/database.md) · [UML](../design/uml.md) · [Data flow](../design/data-flow.md) |

---

## 1. Introduction

### 1.1 Purpose
This document specifies what MENTORX must do (functional requirements) and how well it must do it (non-functional requirements). It's the reference for design, implementation, testing and final evaluation. Every requirement has an ID that the tests and the [traceability matrix](#7-traceability-matrix) refer to.

### 1.2 Problem statement
Most practice platforms give every student the same questions in the same order. Strong students waste time on material they already know. Weak students hit questions that need concepts they haven't learned yet, and nobody reminds them to revisit topics before they forget. Teachers and students have no reliable, per-concept picture of what has actually been learned.

### 1.3 Product scope
MENTORX is a web platform that teaches **Machine Learning** to college students through adaptive multiple-choice practice. It:
- estimates each student's mastery of each concept with a trained knowledge-tracing model,
- selects the next question so it's challenging but achievable for that student,
- recommends what to study next while respecting prerequisites,
- schedules revision when predicted mastery decays,
- shows progress on a dashboard backed only by real data.

**Objectives**
| ID | Objective | Measured by |
|---|---|---|
| OBJ-1 | Predict whether a student will answer a question correctly better than simple baselines | AUC, log loss, calibration vs. a "student's running accuracy" baseline, on held-out students |
| OBJ-2 | Personalise practice so that question difficulty matches the student | Observed correctness rate on served questions close to the target (~65%) |
| OBJ-3 | Improve learning outcomes | Pre/post-test gain, adaptive vs. control group in the pilot |
| OBJ-4 | Keep students practising meaningfully | Weekly active users, D7 return rate, session completion rate |
| OBJ-5 | Be a maintainable, tested, deployed system | CI green, coverage targets, public URL, documented |

### 1.4 Definitions
| Term | Meaning |
|---|---|
| Concept | A unit of knowledge (e.g. "Regularisation"). Each question tests one concept. |
| Prerequisite | Concept A is a prerequisite of B if B can't be learned well without A. The prerequisites form a directed acyclic graph (DAG). |
| Attempt | One answer to one question by one student. Raw, immutable record. |
| Mastery | The model's current estimate (0–1) of the probability that the student answers a medium-difficulty question on a concept correctly. Derived and recomputable. |
| Knowledge tracing (KT) | Modelling a student's knowledge state over time from their answer history. |
| BKT | Bayesian Knowledge Tracing: a hidden Markov model with per-concept learn/guess/slip parameters. |
| Diagnostic | The initial assessment covering every concept once. |
| Session | A run of questions of one type: diagnostic, practice, revision, pre-test or post-test. |
| Target probability | The predicted P(correct) the quiz engine aims for when choosing a question (default 0.65). |
| Model version | A trained, evaluated, serialised model artifact registered in the database. |
| Pilot | The real-user study run after deployment. |

### 1.5 References
- [Project plan](../PROJECT_PLAN.md)
- Corbett & Anderson (1994), *Knowledge tracing: Modeling the acquisition of procedural knowledge*. (BKT)
- Piech et al. (2015), *Deep Knowledge Tracing*. (DKT)
- ASSISTments datasets: https://sites.google.com/site/assistmentsdata/
- EdNet: https://github.com/riiid/ednet
- OWASP ASVS / Top 10 (security), WCAG 2.1 (accessibility)

---

## 2. Overall description

### 2.1 Product perspective
MENTORX is a new, self-contained system: a React single-page app, a FastAPI backend with a PostgreSQL database, and an offline ML pipeline that trains models and exports artifacts that the backend loads. See [architecture](../design/architecture.md).

### 2.2 User classes
| Class | Description | Frequency | Priority |
|---|---|---|---|
| **Student** | College student learning ML. Varied prior knowledge, mostly on phones and laptops. | Daily–weekly | Primary |
| **Admin** | Team member who manages content and models and runs the pilot. Technical. | Occasional | Secondary |
| **Scheduler (system actor)** | Time-based jobs: revision due-ness, weekly reports. | Automatic | — |

### 2.3 Operating environment
- Browsers: current Chrome, Edge, Firefox, Safari (desktop + mobile), at screen widths ≥ 360 px.
- Frontend hosted on Vercel; backend on Render (or equivalent) running Python 3.12; managed PostgreSQL 16+.

### 2.4 Design and implementation constraints
- C-1: Stack is React + TypeScript + Vite + Tailwind; FastAPI + Pydantic; SQLAlchemy + Alembic; PostgreSQL; scikit-learn / XGBoost.
- C-2: Must run within free or student-tier hosting (limited RAM, cold starts). The model artifact must be < 50 MB and load in < 5 s.
- C-3: Public datasets may only be used under their licence terms (EdNet is CC BY-NC 4.0, non-commercial). Raw datasets are never committed to git.
- C-4: No metric, prediction or statistic may be hardcoded or invented. Every number shown must come from the database or a run script.
- C-5: Question content is original. It's not copied from textbooks or exam papers.

### 2.5 Assumptions and dependencies
- A-1: Students answer honestly most of the time. (Rapid-guessing detection mitigates this, but can't eliminate it.)
- A-2: Features that don't depend on the domain, learned from math/English datasets, transfer partially to ML content. This is **tested, not assumed**: in-domain performance is reported separately once pilot data exists.
- A-3: 30–60 pilot users are reachable through the team's college network.
- A-4: Hosting providers' free tiers remain available. If they don't, a paid tier or alternative host is used.

### 2.6 Out of scope (MVP)
Open-ended or code-graded questions; LLM-generated content or chat tutoring; native mobile apps; teacher/class dashboards; payments; subjects other than ML (the design must allow adding them later without schema changes).

---

## 3. Functional requirements

Priority uses **MoSCoW**: **M**ust (MVP), **S**hould (MVP if time allows), **C**ould (post-MVP), **W**on't (this version).

### 3.1 Authentication and profile (AUTH)
| ID | Requirement | Pri |
|---|---|---|
| FR-AUTH-01 | The system shall let a visitor register with full name, email and password, and require explicit acceptance of the privacy notice. | M |
| FR-AUTH-02 | The system shall reject registration if the email is already registered (case-insensitive) or the password is shorter than 8 characters. | M |
| FR-AUTH-03 | The system shall store passwords only as salted Argon2id hashes. | M |
| FR-AUTH-04 | The system shall let a registered user log in with email and password and issue a short-lived access token (≤ 30 min) and a refresh token (≤ 14 days) in an HttpOnly, Secure, SameSite cookie. | M |
| FR-AUTH-05 | The system shall rotate refresh tokens on every use and revoke them on logout. | M |
| FR-AUTH-06 | The system shall return the same error message for "unknown email" and "wrong password". | M |
| FR-AUTH-07 | The system shall rate-limit login attempts per IP and per email (≥ 5 attempts/min triggers a temporary block). | M |
| FR-AUTH-08 | The user shall be able to view and edit profile fields: full name, daily goal (1–100 questions), time zone. | M |
| FR-AUTH-09 | The user shall be able to opt in or out of their data being used for model training (separate from the account-required privacy notice). | M |
| FR-AUTH-10 | The user shall be able to download all their data as JSON. | S |
| FR-AUTH-11 | The user shall be able to delete their account, which permanently deletes their attempts, mastery, sessions, paths and feedback. | M |
| FR-AUTH-12 | The system shall support a password reset by email. | C |

### 3.2 Subjects and content (CONT)
| ID | Requirement | Pri |
|---|---|---|
| FR-CONT-01 | The system shall list active subjects with their concept count. | M |
| FR-CONT-02 | A student shall be able to enrol in a subject. | M |
| FR-CONT-03 | The system shall store concepts and a prerequisite DAG per subject, and reject cyclic prerequisites at load time. | M |
| FR-CONT-04 | Each question shall have one concept, a stem, exactly 4 options, one correct option, an explanation and an author difficulty (1–3). | M |
| FR-CONT-05 | Content shall be loaded from the version-controlled YAML question bank by an idempotent seed command. | M |
| FR-CONT-06 | Editing a question's text or answer shall create a new question version. Past attempts keep a reference to the version they answered. | M |
| FR-CONT-07 | Retired questions shall never be served but their attempts shall be kept. | M |
| FR-CONT-08 | The correct option and explanation shall never be sent to the client before the student answers. | M |

### 3.3 Diagnostic assessment (DIAG)
| ID | Requirement | Pri |
|---|---|---|
| FR-DIAG-01 | After enrolling, the student shall be offered a diagnostic assessment with one diagnostic question per concept, in prerequisite (topological) order. | M |
| FR-DIAG-02 | Each diagnostic question shall offer an "I don't know yet" choice, which is recorded as incorrect with no option selected. | M |
| FR-DIAG-03 | The diagnostic shall not show correctness after each question (to reduce anxiety and guessing). It shows a summary at the end. | S |
| FR-DIAG-04 | On completion, the system shall compute initial mastery for every concept and generate the first learning path. | M |
| FR-DIAG-05 | The student shall be able to skip the diagnostic. Mastery then starts from the model's cold-start prior. | S |
| FR-DIAG-06 | A diagnostic that's interrupted shall be resumable from the next unanswered question. | S |

### 3.4 Adaptive quiz engine (QUIZ)
| ID | Requirement | Pri |
|---|---|---|
| FR-QUIZ-01 | A student shall be able to start a practice session either on a specific concept or in "recommended" mode (the system picks concepts from the learning path). | M |
| FR-QUIZ-02 | For each next question, the system shall predict P(correct) for every eligible candidate with the active model and choose randomly among the 3 candidates closest to the target probability (default 0.65, configurable). | M |
| FR-QUIZ-03 | Eligible candidates shall exclude retired questions, questions answered in the current session, and questions answered correctly in the last 7 days (configurable). | M |
| FR-QUIZ-04 | If no candidates remain for a concept, the system shall fall back to the least recently seen question and log a "content exhausted" event. | M |
| FR-QUIZ-05 | The system shall record the predicted probability and the model version for every served question **before** the answer is submitted. | M |
| FR-QUIZ-06 | The system shall measure response time server-side (from serving to answer). | M |
| FR-QUIZ-07 | An answer shall only be accepted for the question currently served in that session, once. | M |
| FR-QUIZ-08 | After each answer, the system shall return correctness, the correct option, the explanation and the updated mastery of the concept. | M |
| FR-QUIZ-09 | A practice session shall end after 10 questions (configurable) or when the student ends it. | M |
| FR-QUIZ-10 | Students in the pilot's **control** group shall get questions chosen uniformly at random from eligible candidates (same concepts, same session length). Everything else stays identical. | M |
| FR-QUIZ-11 | The student shall be able to flag a question as wrong or unclear with an optional comment. | S |

### 3.5 Knowledge estimation (KT)
| ID | Requirement | Pri |
|---|---|---|
| FR-KT-01 | The system shall estimate P(correct) for a (student, question, time) triple using only attempts before that time. | M |
| FR-KT-02 | The same feature-building code shall be used for training and for serving. | M |
| FR-KT-03 | After every attempt, the system shall recompute and store the mastery of the attempted concept, tagged with the model version. | M |
| FR-KT-04 | Mastery shall decay with time without practice (via time-since-last-attempt features or an equivalent model mechanism). Displayed mastery shall be recomputed when it's read if it's older than 24 h. | M |
| FR-KT-05 | Exactly one model version shall be active at a time. Admins can switch the active version without redeploying. | S |
| FR-KT-06 | If the primary model fails to load, the system shall fall back to the logistic-regression model trained on the same data (shipped as a separate artifact); if that also fails, to the training-set average probability. It shall log an error, and when on the last fallback it shall show no ML-based claims in the UI. *(Changed in M4: the originally planned smoothed-accuracy heuristic was badly calibrated, with ECE 0.12 on both benchmarks, and on EdNet it was worse than the constant average; see ml/reports/models.)* | M |
| FR-KT-07 | The offline pipeline shall train and compare at least Logistic Regression, a tree ensemble (Random Forest or gradient boosting) and BKT. Splits must be student-level and the training/evaluation reproducible from a config and seed. | M |
| FR-KT-08 | The evaluation report shall include AUC-ROC, accuracy, F1, log loss, Brier score, a reliability diagram and bootstrap 95% CIs. | M |
| FR-KT-09 | A DKT model shall be benchmarked on public data. | C |

### 3.6 Learning path (PATH)
| ID | Requirement | Pri |
|---|---|---|
| FR-PATH-01 | The system shall generate an ordered list of up to 5 recommended concepts per subject with a reason for each: *weak*, *prerequisite*, *revision* or *new*. | M |
| FR-PATH-02 | A concept shall only be recommended as *weak* or *new* when all its prerequisites have mastery ≥ 0.6 (configurable). Otherwise its weakest unmet prerequisite is recommended instead, with reason *prerequisite*. | M |
| FR-PATH-03 | Each recommended concept shall carry a target difficulty (1–3) derived from its mastery band. | M |
| FR-PATH-04 | The learning path shall be regenerated after the diagnostic, after each completed session, and when revision items become due. | M |
| FR-PATH-05 | The system shall keep previous paths (not overwrite them) so recommendation effectiveness can be evaluated. | M |
| FR-PATH-06 | Each recommendation shall show a plain-language explanation (e.g. "Regularisation needs Bias & Variance, which you're at 45% on"). | S |

### 3.7 Revision (REV)
| ID | Requirement | Pri |
|---|---|---|
| FR-REV-01 | A concept shall become *due for revision* when its peak mastery reached ≥ 0.8 and its current predicted mastery has fallen below 0.6 (both configurable). | M |
| FR-REV-02 | The student shall see a revision queue ordered by how far mastery has fallen. | M |
| FR-REV-03 | A revision session shall serve 5 questions from due concepts. | M |
| FR-REV-04 | The system shall show mastery before and after each revision session. | S |
| FR-REV-05 | The system shall show a calendar of projected revision dates per concept (when predicted mastery is expected to cross the threshold). | C |

### 3.8 Dashboard and analytics (DASH)
| ID | Requirement | Pri |
|---|---|---|
| FR-DASH-01 | The dashboard shall show overall progress: mean mastery across concepts, and concepts mastered (≥ 0.8) out of the total. | M |
| FR-DASH-02 | The dashboard shall show a concept mastery map laid out as the prerequisite graph and coloured by mastery. | M |
| FR-DASH-03 | The dashboard shall list the 3 strongest and 3 weakest concepts (with at least 3 attempts each). | M |
| FR-DASH-04 | The dashboard shall show accuracy and mean mastery over time (daily, last 30 days). | M |
| FR-DASH-05 | The dashboard shall show session history with type, date, questions, accuracy and mastery change. | M |
| FR-DASH-06 | The dashboard shall show the current learning path and revision queue. | M |
| FR-DASH-07 | The dashboard shall show an activity heatmap (questions answered per day, last 12 weeks). | S |
| FR-DASH-08 | Empty states shall explain what to do. The system shall never show placeholder numbers. | M |
| FR-DASH-09 | Admins shall see pilot metrics: WAU, D1/D7 retention, completion rate, pre/post gain by group, live model AUC and calibration. | M |

### 3.9 Engagement (ENG)
| ID | Requirement | Pri |
|---|---|---|
| FR-ENG-01 | The system shall count a day toward the streak when the student completes their daily goal of *valid* answers in their time zone. | M |
| FR-ENG-02 | An answer is *valid* if its response time is ≥ 3 s and it isn't part of a run of ≥ 5 consecutive answers under 3 s. | M |
| FR-ENG-03 | The system shall show the current streak, longest streak and today's progress toward the goal. | M |
| FR-ENG-04 | The system shall award milestone achievements tied to learning (first concept mastered, all prerequisites of a concept mastered, a revised concept recovered). | C |
| FR-ENG-05 | The system shall show a weekly report: questions, accuracy, concepts improved, mastery change. | S |
| FR-ENG-06 | The system shall offer an adaptive challenge: 5 questions targeted at P(correct) ≈ 0.4. | C |

### 3.10 Pilot and feedback (PILOT)
| ID | Requirement | Pri |
|---|---|---|
| FR-PILOT-01 | When the pilot is active, new users shall be randomly assigned to the *adaptive* or *control* group (50/50) at registration. The assignment is stored and never changed. | M |
| FR-PILOT-02 | The system shall provide a pre-test and a post-test from two parallel forms, counterbalanced across users. | M |
| FR-PILOT-03 | Users shall be able to submit feedback (1–5 rating, category, message) from any page. | M |
| FR-PILOT-04 | The system shall present a SUS usability questionnaire after the post-test. | S |
| FR-PILOT-05 | Admins shall be able to export pseudonymised attempt data of consenting users (no names or emails) for model training. | M |

---

## 4. Non-functional requirements

| ID | Category | Requirement | Verification |
|---|---|---|---|
| NFR-PERF-01 | Performance | `next question` and `submit answer` API p95 latency ≤ 300 ms (excluding cold starts) with 50 concurrent users | Locust load test |
| NFR-PERF-02 | Performance | Dashboard initial load (LCP) ≤ 2.5 s on a mid-range phone over 4G | Lighthouse |
| NFR-PERF-03 | Performance | Frontend initial JS ≤ 250 KB gzipped | Build report |
| NFR-SEC-01 | Security | All traffic over HTTPS; HSTS in production | Config review |
| NFR-SEC-02 | Security | All input validated by Pydantic schemas; ORM-parameterised SQL only | Code review, tests |
| NFR-SEC-03 | Security | Authorization checked on every resource: a student can only access their own sessions, attempts and mastery | API tests per endpoint |
| NFR-SEC-04 | Security | Secrets only in environment variables; none in git | CI secret scan |
| NFR-SEC-05 | Security | CORS restricted to the deployed frontend origin | Config test |
| NFR-SEC-06 | Security | Dependencies checked for known vulnerabilities in CI | pip-audit / npm audit |
| NFR-PRIV-01 | Privacy | Collect only name, email and learning interactions. No tracking pixels or third-party analytics. | Review |
| NFR-PRIV-02 | Privacy | Training exports exclude PII and use a salted hash as the student ID | Export test |
| NFR-PRIV-03 | Privacy | Account deletion removes all personal records within one request | API test |
| NFR-REL-01 | Reliability | Raw attempts are append-only. Mastery and paths can be rebuilt from attempts with a command. | Rebuild test |
| NFR-REL-02 | Reliability | Database has daily automated backups (provider feature) | Provider config |
| NFR-REL-03 | Reliability | Unhandled errors return a JSON error with a request ID, never a stack trace | API test |
| NFR-USE-01 | Usability | A new student can register and start the diagnostic in ≤ 2 minutes without help | Usability test (5 users) |
| NFR-USE-02 | Usability | SUS score ≥ 70 in the pilot | SUS survey |
| NFR-USE-03 | Usability | Responsive layout with no horizontal scroll at 360 px; touch targets ≥ 44 px | Manual + Playwright viewport test |
| NFR-ACC-01 | Accessibility | WCAG 2.1 AA: contrast, keyboard navigation, focus visible, labels, no colour-only meaning (mastery map shows % text too) | axe-core in tests + manual |
| NFR-MAINT-01 | Maintainability | Backend service-layer test coverage ≥ 80%; CI must pass before merge | Coverage report |
| NFR-MAINT-02 | Maintainability | Layered architecture: routers contain no business logic or SQL | Code review |
| NFR-MAINT-03 | Maintainability | Database changes only via Alembic migrations | Review |
| NFR-ML-01 | ML reproducibility | Every reported metric is reproducible from `ml/scripts` with a committed config and seed | Re-run check |
| NFR-ML-02 | ML integrity | No leakage: student-level splits; difficulty and other target statistics fitted on training data only; features use only past attempts | Unit tests on feature builder |
| NFR-ML-03 | ML inference | Inference for 50 candidates ≤ 50 ms; artifact ≤ 50 MB | Benchmark test |
| NFR-ML-04 | ML calibration | Selected model's expected calibration error ≤ 0.05 on validation data, or it's recalibrated | Evaluation report |
| NFR-PORT-01 | Portability | Whole stack runs locally with documented commands (no Docker required) | README check |
| NFR-OBS-01 | Observability | Structured logs with request ID, user ID (pseudonymous) and latency for every request | Log review |

---

## 5. External interface requirements

### 5.1 User interfaces
Main screens: Landing · Register/Login · Onboarding (subject, goal, consent) · Diagnostic · Practice/Revision quiz · Answer feedback · Dashboard · Learning path · Mastery map · Revision queue · Session history · Profile & privacy · Feedback dialog · Admin pilot dashboard. Wireframes are produced in M8. All screens follow the design tokens in `frontend/src/index.css` and support light and dark mode.

### 5.2 Software interfaces
- REST/JSON API under `/api/v1`, documented automatically via OpenAPI at `/docs`. The endpoint list is in [architecture §4](../design/architecture.md#4-api-overview).
- PostgreSQL via SQLAlchemy 2.x (psycopg 3 driver).
- Model artifacts: `joblib` file + `metadata.json` (feature list, training data hash, metrics, created date).

### 5.3 Communication interfaces
HTTPS only. Access token in the `Authorization: Bearer` header; refresh token in an HttpOnly cookie scoped to `/api/v1/auth`.

---

## 6. Data requirements
- **Raw vs derived:** `attempts` is the source of truth. `mastery`, `mastery_snapshots` and `learning_paths` are derived and can be rebuilt.
- **Retention:** data is kept while the account exists, and deleted with the account.
- **Training data:** only from users with `consent_research = true`, exported pseudonymised.
- **Public datasets:** stored only under `ml/data/` (gitignored). Their source, licence and download date are recorded in `docs/datasets.md`.
- The full schema is in [database.md](../design/database.md).

---

## 7. Traceability matrix

| Requirement group | Use cases | User stories | Milestone | Test location |
|---|---|---|---|---|
| FR-AUTH | UC-01, UC-02, UC-11 | US-01 – US-05 | M5 | `backend/tests/api/test_auth*.py` |
| FR-CONT | UC-12 | US-06, US-30 | M2, M5 | `backend/tests/unit/test_question_bank.py`, `tests/integration/test_seed.py` |
| FR-DIAG | UC-03 | US-07 – US-09 | M6 | `backend/tests/integration/test_diagnostic.py` |
| FR-QUIZ | UC-04 | US-10 – US-14 | M6 | `backend/tests/unit/test_question_selector.py`, `tests/api/test_sessions.py` |
| FR-KT | UC-05, UC-13 | US-15, US-31, US-32 | M3, M4, M6 | `ml/tests/`, `backend/tests/unit/test_inference.py` |
| FR-PATH | UC-06 | US-16 – US-18 | M7 | `backend/tests/unit/test_recommender.py` |
| FR-REV | UC-07 | US-19, US-20 | M7 | `backend/tests/unit/test_revision.py` |
| FR-DASH | UC-08, UC-14 | US-21 – US-24, US-33 | M5–M8 | `backend/tests/api/test_dashboard.py`, `frontend/src/**/*.test.tsx` |
| FR-ENG | UC-09 | US-25 – US-27 | M10 | `backend/tests/unit/test_streaks.py` |
| FR-PILOT | UC-10, UC-14 | US-28, US-29, US-34 | M11 | `backend/tests/integration/test_pilot.py` |
| NFR-* | — | — | M9 | Load tests, Lighthouse, axe, security checks |

This matrix is updated as tests are written: every Must requirement needs at least one test before M9 is closed.
