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
| Adaptive diagnostic (10 questions) or skill check (6 questions) | `Assessment` | `POST /assessments`, `GET /assessments/{id}/next`, `POST .../answer` |
| AI skill diagnosis, with how each diagnostic question was chosen | `Diagnosis` | `GET /diagnosis` |
| Dashboard: continue, overview, streak + daily goal, Mixed practice, recommendations, skill map | `Dashboard` | `GET /dashboard` |
| Learning module per skill (concept, video, notes, worked examples, guided practice, assessment) | `Skill` | `GET /skills/{id}`, `PATCH /skills/{id}/mode`, `POST /resources/{id}/complete` |
| Adaptive / guided practice with skill hints and AI hints; Mixed practice | `Practice` | `POST /practice` (`kind`: `skill` or `mixed`), `GET .../next`, `POST .../hint?ai=`, `POST .../answer`, `POST .../end` |
| AI explanation of an answered question | `Practice`, `Skill` (recent mistakes) | `GET /ai/status`, `POST /ai/explain` |
| Reassessment with fresh questions, spaced revision | `Assessment`, `ReassessmentResult` | same as assessments, `kind=reassessment` |
| Learning path, analytics, resources, profile (pace, daily goal) | `Path`, `Analytics`, `Resources`, `Profile` | `GET /path`, `GET /analytics`, `GET /resources`, `PATCH /profile`, `PUT /goal` |
| Content admin, live model monitor, AI texts | `Admin` | `/admin/*` (role admin or `ADMIN_EMAILS`) |

## Content coverage

`scripts/seed_math.py` loads every dataset question and records why any question can't be served.
On the full FoundationalASSIST export: **132 available skills** (5+ usable single-skill questions),
**2,942 usable single-skill questions** and **354 multi-skill questions** (before v2.1: 90 skills,
1,942 questions, no multi-skill questions).

- **Answer types** (`answers.py`, `mathexpr.py`): numeric; multiple choice (and drop-down);
  check-all; **algebraic** (equivalence, plus the key's form when the question says factor, expand,
  fewer terms, ...); **numeric expression** (value); **exact fraction** (the written form); **exact
  match** (text, numbers by value, short algebra by equivalence and form). Typed input passes a
  strict token allowlist before SymPy sees it.
- **Spreadsheet damage** in the export is undone: "6-May" was 5/6, "Jan-40" was 1/40, "1E+12" is 10^12.
- **Images** (`html.py`): WIRIS formula images become real MathML (their formula is stored in the
  image). Other images are served from allowlisted HTTPS hosts only after `scripts/check_images.py`
  confirmed they load (868 of 878 did on 2026-11-12). The CSP allows exactly those hosts.
- **Multi-skill questions** are used only in Mixed practice. Their single score is never counted as
  evidence for each of their skills; the model still receives all their skills, as in training.
- **Still excluded** (and listed on the admin page): ordering questions (the correct order can't be
  split reliably), questions with several blanks, missing answer keys, and images that don't load.
- **Notes and worked examples** for every available skill: 18 standards written earlier, 83 more
  added in v2.1 (`seeddata/resources_grade*.yaml`, labelled "AI-assisted, pending teacher review").

## Machine learning

- **Model served:** DKT-Q, an LSTM over (skill, response) and (question, response) embeddings plus the previous attempt's hints, answer reveal and time gap, with a per-question difficulty bias. It is trained in `ml/notebooks/02_foundationalassist_knowledge_tracing.ipynb`. Test AUC **0.812**, accuracy 0.749 on held-out students (local CPU run; a Kaggle GPU run gave 0.811). Plain DKT (AUC 0.773) can be served instead with `KT_MODEL=dkt`.
- **Serving:** `ml/scripts/export_kt.py` turns the PyTorch checkpoints into `.npz` weights plus `kt_meta.json` (index maps, input convention, metrics), and proves the NumPy forward pass in `backend/app/ml/dkt.py` matches PyTorch (max difference 2×10⁻⁷). The model is loaded once at startup and never trained by the app.
- **Inference service** (`app/tutor/kt.py`): turns the student's interaction log into the model's input convention (multi-skill questions with all their skills), predicts P(correct) for candidate questions, and averages per skill over single-skill questions. If the artifacts are missing, `available=false` and every screen shows observed data only.
- **Where the model is used:**
  1. **Adaptive diagnostic** (`assess.choose_diagnostic_item`): after each answer, among the least-covered domains, the question with the largest p(1−p), i.e. the one the model is least sure about (the most informative, as in computerised adaptive testing). A wrong answer first triggers a check of a curated prerequisite (at most 2 per diagnostic). The first question has no history, so it is a typical grade-level question chosen by historical success rate. Every choice and its reason is stored and shown.
  2. **Practice question choice:** the question closest to the mode's target success (0.80 / 0.70 / 0.60 / 0.50).
  3. **Ordering untested skills** in recommendations (never labelling them).
  4. **Second opinion in the diagnosis:** a weakness/strength label needs the model not to disagree.
- **Live monitoring** (`admin.model_monitor`, admin "Model monitor" tab): every prediction is stored before the answer, so AUC, log loss, Brier score, accuracy and a calibration plot on real students are honest out-of-sample numbers, shown next to the offline test results. Practice narrows the range of predictions on purpose, which usually lowers live AUC; calibration is the better check there.
- **The original Kaggle checkpoint** (`dkt_best.pth`, 194 skills, 161,409 parameters) was never downloaded from `/kaggle/working`, so it isn't in the repo. The DKT here is the same architecture family, retrained on corrected data (all 224 skills, multi-skill questions kept), and reaches the same test AUC.

## AI tutor (optional, `app/tutor/ai.py`, `llm.py`)

- OpenRouter's OpenAI-compatible API with free models: `AI_MODEL` first, then `AI_FALLBACK_MODELS` when it is busy (free models are often rate-limited upstream). No key = switched off, buttons hidden.
- **Explanations** exist only for answered questions (requested by interaction id). One text per question and kind of answer (correct / revealed / each distinct wrong answer), cached, so repeats cost nothing.
- **AI hints** are generated while a question is open. The server rejects any hint containing the answer (its value, expression, the correct option's text or letter) and shows the skill hint instead. Any hint marks the answer as "with help", matching the model's training label.
- Every text is labelled AI-generated; admins can hide any text; each student has a daily limit (`AI_DAILY_LIMIT`). Only the question, its answer and the student's response are sent: no name, email or id.

## Rules (all in pure functions with unit tests)

- **Diagnosis** (`state.diagnose`): no answers in a skill means **Needs Assessment**, whatever the model says. Recent observed accuracy ≥ 75% (2+ answers) with the model not disagreeing means **Likely Strength**. Accuracy ≤ 45% with the model not disagreeing means **Potential Weakness**. Anything else is **Developing**. Evidence: none / limited (1–2 answers) / moderate (3–5) / strong (6+). Only single-skill answers count.
- **Learning mode** (`state.learning_mode`), per skill: from recent accuracy minus a hint penalty, never from speed. The student's pace preference shifts it one level, and a per-skill override is allowed. Mixed practice uses guided / independent / advanced from the pace preference.
- **Practice** (`practice.adjust`): two correct in a row means one level harder, two wrong means one level easier, otherwise stay, bounded by easy and hard. Among unused questions at that level, the model picks the one closest to the mode's target success. Fallbacks (another level, unrated, then review of earlier questions) are shown to the student.
- **Reassessment:** only never-seen questions. The outcome compares the first ≤5 answers in the skill with the reassessment. ≥ 80%, or ≥ 70% with a gain of 15+ points, counts as improved. A gain of 15+ points below that is progressing; anything else is not improved. A score of 80%+ completes the skill.
- **Spaced revision** (`assess.revision_interval`): a completed skill is due for review after 7 days; each successful review doubles the gap (7, 14, 28, 56, capped at 60 days); a failed review keeps it due.
- **Streak and daily goal** (`views.streak`): days in a row with at least one answer (UTC days); today's answers against the student's daily goal (1–200, default 10).
- **Recommendations** (`recommend.generate`): focus topic, then evidence-backed weaknesses, revision due, developing skills, untested curated prerequisites of weak skills, next objectives after completed skills, and untested core skills (ordered by model estimate). Each one stores its plain-language reason.
- **Resources and AI help never change estimates.** Only answers do.

## What is original, mocked or limited (honest list)

- **Concept notes and worked examples** are original MENTORX content written with AI assistance (Claude): 18 standards in `resources.yaml` and 83 in `resources_grade4_6.yaml`, `resources_grade7.yaml`, `resources_grade8.yaml` (the latter labelled "AI-assisted, pending teacher review" in the app). A teacher review is still to do. Every skill also links to its genuine Common Core standard page.
- **No videos:** no verified video links were added. The video step says so, and admins can add videos.
- **Skill hints** are the key idea from the notes. **AI hints and explanations** come from free language models and can be wrong; they are labelled and moderated, never used for scoring.
- **Prerequisites** are curated from Common Core grade progressions (`seeddata/prerequisites.yaml`), never inferred from performance.
- **Images** load from the dataset's own servers; if those servers change, `check_images.py` and a reseed take broken images out.
- **Database:** PostgreSQL (the existing stack). The new tables use portable column types, but the app as a whole is not tested on SQLite.
- Some dataset questions refer to earlier parts of their problem set ("Choose one equation…"). Admins can switch any question off.
