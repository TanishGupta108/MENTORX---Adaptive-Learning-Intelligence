# MENTORX v2: the adaptive Mathematics tutor

The student-facing product since November 2026. API under `/api/v2` (auth stays on `/api/v1/auth`),
code in `backend/app/tutor/`, screens in `frontend/src/pages/`. The v1 engine for the Machine Learning
subject (`/api/v1/sessions`, `/learning`, ...) is still in the code and its tests still pass,
but the UI no longer uses it, and seeding Mathematics hides the ML subject.

## The student journey

| Step | Screen | Backend |
|---|---|---|
| Landing, register, sign in | `Landing`, `Auth` | `/api/v1/auth/*` (Argon2id passwords, 30-min JWT, HttpOnly refresh cookie) |
| Onboarding: goal (assess / improve / one topic), Mathematics card with real skills, learning goal | `Onboarding` | `POST /onboarding`, `GET /subject` |
| Diagnostic (10 questions) or skill check (6 questions) | `Assessment` | `POST /assessments`, `GET /assessments/{id}/next`, `POST .../answer` |
| AI skill diagnosis | `Diagnosis` | `GET /diagnosis` |
| Dashboard | `Dashboard` | `GET /dashboard` |
| Learning module per skill (concept, video, notes, worked examples, guided practice, assessment) | `Skill` | `GET /skills/{id}`, `PATCH /skills/{id}/mode`, `POST /resources/{id}/complete` |
| Adaptive / guided practice with hints | `Practice` | `POST /practice`, `GET .../next`, `POST .../hint`, `POST .../answer`, `POST .../end` |
| Reassessment with fresh questions | `Assessment`, `ReassessmentResult` | same as assessments, `kind=reassessment` |
| Learning path, analytics, resources, profile | `Path`, `Analytics`, `Resources`, `Profile` | `GET /path`, `GET /analytics`, `GET /resources`, `PATCH /profile`, `PUT /goal` |
| Content admin | `Admin` | `/admin/*` (role admin or `ADMIN_EMAILS`) |

## Machine learning

- **Model served:** DKT-Q, an LSTM over (skill, response) and (question, response) embeddings plus the previous attempt's hints, answer reveal and time gap, with a per-question difficulty bias. It is trained in `ml/notebooks/02_foundationalassist_knowledge_tracing.ipynb`. Test AUC **0.812**, accuracy 0.749 on held-out students (local CPU run; a Kaggle GPU run gave 0.811). Plain DKT (AUC 0.773) can be served instead with `KT_MODEL=dkt`.
- **Serving:** `ml/scripts/export_kt.py` turns the PyTorch checkpoints into `.npz` weights plus `kt_meta.json` (index maps, input convention, metrics), and proves the NumPy forward pass in `backend/app/ml/dkt.py` matches PyTorch (max difference 2×10⁻⁷). The model is loaded once at startup and never trained by the app.
- **Inference service** (`app/tutor/kt.py`): turns the student's interaction log into the model's input convention, predicts P(correct) for candidate questions, and averages per skill. If the artifacts are missing, `available=false` and every screen shows observed data only.
- **The original Kaggle checkpoint** (`dkt_best.pth`, 194 skills, 161,409 parameters) was never downloaded from `/kaggle/working`, so it isn't in the repo. The DKT here is the same architecture family, retrained on corrected data (all 224 skills, multi-skill questions kept), and reaches the same test AUC.

## Rules (all in pure functions with unit tests)

- **Diagnosis** (`state.diagnose`): no answers in a skill means **Needs Assessment**, whatever the model says. Recent observed accuracy ≥ 75% (2+ answers) with the model not disagreeing means **Likely Strength**. Accuracy ≤ 45% with the model not disagreeing means **Potential Weakness**. Anything else is **Developing**. Evidence: none / limited (1–2 answers) / moderate (3–5) / strong (6+).
- **Learning mode** (`state.learning_mode`), per skill: from recent accuracy minus a hint penalty, never from speed. The student's pace preference shifts it one level, and a per-skill override is allowed.
- **Practice** (`practice.adjust`): two correct in a row means one level harder, two wrong means one level easier, otherwise stay, bounded by easy and hard. Among unused single-skill questions at that level, the model picks the one closest to the mode's target success (0.80 / 0.70 / 0.60 / 0.50). Fallbacks (another level, unrated, then review of earlier questions) are shown to the student.
- **Reassessment:** only never-seen questions. The outcome compares the first ≤5 answers in the skill with the reassessment. ≥ 80%, or ≥ 70% with a gain of 15+ points, counts as improved. A gain of 15+ points below that is progressing; anything else is not improved. A score of 80%+ completes the skill and schedules revision in 7 days.
- **Recommendations** (`recommend.generate`): focus topic, then evidence-backed weaknesses, revision due, developing skills, untested curated prerequisites of weak skills, next objectives after completed skills, and untested core skills (ordered by model estimate). Each one stores its plain-language reason.
- **Resources never change estimates.** Only answers do.

## What is original, mocked or limited (honest list)

- **Concept notes and worked examples** are original MENTORX content for 18 core standards (`app/tutor/seeddata/resources.yaml`). Every available skill also links to its genuine Common Core standard page. Other skills say plainly that no notes exist yet.
- **No videos:** no verified video links were added. The video step says so, and admins can add videos.
- **Hints** are skill-level key ideas (or a general strategy tip), because the dataset has no per-question hints.
- **Prerequisites** are curated from Common Core grade progressions (`seeddata/prerequisites.yaml`), never inferred from performance.
- **Database:** PostgreSQL (the existing stack). The new tables use portable column types, but the app as a whole is not tested on SQLite.
- Some dataset questions refer to earlier parts of their problem set ("Choose one equation…"). Admins can switch any question off.
