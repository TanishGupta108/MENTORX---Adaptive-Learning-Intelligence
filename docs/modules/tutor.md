# MENTORX v3: the adaptive tutor (Mathematics, Geography map skills)

The student-facing product. API under `/api/v2` (auth stays on `/api/v1/auth`), code in
`backend/app/tutor/`, screens in `frontend/src/pages/`. The v1 engine for the Machine Learning
subject (`/api/v1/sessions`, `/learning`, ...) is still in the code and its tests still pass, but
the UI no longer uses it, and seeding a v3 subject hides the ML subject.
Geography (Slepemapy.cz data) is documented in `docs/modules/geography.md`.

## Subjects

- Subjects: `MATH` (FoundationalASSIST) and `GEO` (map skills). A subject is visible only when its
  row is active, i.e. after its seed ran (`scripts/seed_math.py`, `scripts/seed_geography.py`).
  Seeding one never hides the other (`subjects.V2_SUBJECTS`).
- `StudentProfile.subject_id` is the student's **current subject**. `Enrollment(user, subject)`
  lists the subjects they started; `Enrollment.diagnostic_completed_at` is the per-subject
  placement-check flag.
- Every "for the student" read (home, catalog, skills, diagnosis, progress, path, resources, mixed
  practice, reviews, diagnostic, recommendations, model predictions) is scoped to the current
  subject. Endpoints addressed by a skill, item, session or assessment id work in any active subject.
- Streak, daily goal, weekly-practice goal and the AI daily limit count across all subjects.
- One knowledge-tracing model per subject (`KT_SUBJECTS`, MATH defaults to `KT_ARTIFACTS_DIR`).
  Each model only sees its own subject's answers. A subject without model files shows observed
  results only.
- Credits (`GET /subjects` → `attribution`, `notice`) are fixed text in `app/tutor/subjects.py`.
- Grades exist for Maths only (onboarding grade, Skills filter). Mixed practice is Maths only.

## The student journey (API)

| Step | Backend |
|---|---|
| Register, sign in | `/api/v1/auth/*` |
| Onboarding: subject (when 2+ are active), grade 3–8 or not sure (Maths), pace, goal | `POST /onboarding` (`subject_code`, `grade`, `pace_preference`), `GET /subjects` |
| Home: one next step, up to 2 more, reviews due, pace suggestion, diagnosis summary, streak | `GET /home`, `POST /home/pace-suggestion` |
| Switch subject (enrols the first time) | `PUT /profile/subject` |
| Placement check (adaptive diagnostic) or skill check | `POST /assessments`, `GET .../next`, `POST .../answer` |
| Diagnosis report | `GET /diagnosis` |
| Skills list, skill page | `GET /subject`, `GET /skills/{id}`, `PATCH /skills/{id}/mode`, `POST /resources/{id}/complete` |
| Practice: one skill, mixed, or review | `POST /practice` (`kind`: `skill`, `mixed`, `review`), `GET .../next`, `POST .../hint?ai=`, `POST .../answer`, `POST .../end` |
| AI explanation of an answered question | `GET /ai/status`, `POST /ai/explain` |
| Progress | `GET /analytics` (`/dashboard` and `/path` still exist, scoped) |
| Admin (role admin or `ADMIN_EMAILS`) | `/admin/*`, `?subject=MATH\|GEO` on overview, skills, model; `POST /admin/ai/test` |

`GET /home` returns `next` (a `NextAction`: kind, plain title, one-sentence reason behind "Why?",
`progress_hint`, and a `start` the client launches directly). Priority: resume an unfinished
session > placement check not done > reviews due > a stuck skill's unmet building block >
the current recommendations (no answers → skill check; mastered but not completed → the short
check; step-by-step mode with no notes read yet → learn; else practice). Recommendations are
regenerated on read when older than 6 hours. Home runs at most 15 SQL statements (tested with 50
answers).

## Answer checking (`answers.py`, `mathexpr.py`)

Types: numeric; multiple choice (and drop-down; Geography map questions too); check-all;
ordering; algebraic (equivalence, plus the key's form when the question says factor, expand, ...); numeric
expression; exact fraction (the written form); exact match. Typed input passes a strict token
allowlist before SymPy sees it. Spreadsheet damage in the export is undone ("6-May" was 5/6).

**Numeric policy** (numeric, and the numeric paths of numeric expression and exact match):

1. The exact value is always accepted, in any form (11/3, 3 2/3, 22/6).
2. Truncated keys are recovered: a key with ≥ 6 decimals whose simplest nearby fraction
   (denominator ≤ 1000) repeats and rounds back to the key is treated as that fraction
   (-1.333333333 → -4/3). Done at check time and in `numeric_key` at seed time.
3. Rounded decimals, only for repeating values and when no fraction is asked for: a decimal with
   ≥ 2 places is accepted if the true value rounds (half up) to it. 3.67, 3.667 are right for 11/3;
   3.66 (truncated) and 3.7 (1 place) are not. Never for terminating values (9.68 for 9.681 is wrong).
4. An explicit rounding instruction ("nearest tenth", "two decimal places", "nearest whole
   percent", "nearest cent", ...) wins: an answer with at least that many places is right when it
   rounds to the key. "If the answer is not a whole number" is not an instruction.
5. "Write your answer as a fraction": exact values only.
6. Percent: when the question mentions % or "percent", "22%" means 22; otherwise 50% means 0.5.
7. Harmless decoration is removed first: "$", "x =", a unit after the number (a word right after
   the blank in the question, or a common unit), "1 000", "- 3", "(5)".

**Ordering questions** (`ordering.py`): FoundationalASSIST stores no key for them (for all 32 the
"answer" column repeats the options in no particular order). The order is recovered at seed time
from `Interactions.csv`: at least 20 answers marked correct, at least 60% of them giving one same
order, every item matched to exactly one option (by text, or by exact value for numbers written
as formulas), never from letter answers ("C. , A. , B."), and for number lists the order must also
equal the sort the question asks for. 13 of 32 pass (2026-11-14); the rest stay excluded with
the reason (`ordering_key_not_recovered: ...`). Students reorder items with up/down buttons;
only the exact order is right; items are never shown already in order (or reversed).

The correct answer is shown exactly first, with a rounded hint: `11/3 (about 3.67)`.
`scripts/regrade.py` re-checks old answers with these rules (wrong → right only, audited with
`response.regraded_at`, idempotent; AI explanations of those answers are hidden).

## Personalization rules (thresholds in `core/config.py`)

- **Diagnosis** (`state.diagnose`): no answers → **Not tried yet**, whatever the model says. Recent
  observed accuracy ≥ 75% (2+ answers) with the model not disagreeing (≥ `MODEL_AGREE_THRESHOLD`
  0.6) → **Strong**. ≤ 45% with 2+ answers and the model not disagreeing → **Needs practice** (one
  wrong answer is not enough). Otherwise **Getting there**. Only single-skill answers count.
- **Mastery** (observed only): the last 3 answers right, ≥ 80% of the last 8 right, ≥ 5 answers.
  `to_go` = correct answers in a row still needed ("3 more correct to master"). Mastered but not
  completed → the next step is the 5-question check; passing it (≥ 80%) completes the skill.
- **Stuck (wheel-spinning)**: ≥ 10 answers in the skill, never mastered, and fewer than half of the
  last 6 right; or 3 wrong in a row at the easy level in one session. Then the plan changes: a
  curated building block that isn't Strong yet, else the notes and worked example and a
  step-by-step session.
- **Learning mode** (per skill, never from speed): recent accuracy minus a penalty for hints used in
  the same recent window (last 6). Pace shifts it one level; a per-skill override is allowed. A
  "not improved" check sets step-by-step mode until the next passed check.
- **Session length and early stop**: 6 / 8 / 10 questions for more support / balanced / challenge.
  A skill session stops early after ≥ 5 answers when the mastery rule holds ("mastered"), at once on
  3 wrong in a row at easy ("stuck"), or when no new question is left ("enough"). Mixed: 8.
- **Practice difficulty**: two right in a row → one level harder, two wrong → one easier. Among
  unused questions at that level the model picks the one closest to the mode's target success
  (0.80 / 0.70 / 0.60 / 0.50). Students see a plain sentence ("A medium question, because your last
  two were right."); the model numbers are in `selection.technical`.
- **Reviews (spaced retrieval + interleaving)**: when a skill first becomes Strong or is completed,
  a review is due 3 days later. A review session serves 2 new questions from each due skill (most
  overdue first, at most 4 skills), interleaved. Both right → the next interval (3, 7, 14, 30, 60
  days); otherwise review again tomorrow from the start. An early (not due) passed check keeps the
  stage; failing a check of a completed skill un-completes it.
- **Pace suggestion**: over the last 20 single-skill answers from ≥ 2 sessions: ≥ 85% right and
  < 10% hints → suggest "challenge"; < 50% right or > 30% answers revealed → suggest "more support".
  One tap to accept; never automatic; hidden 14 days after a choice.
- **Grade**: the placement check starts at grade − 1 (at least 3; the lowest grade when "not
  sure"); new objectives and untested core skills near the student's grade come first.
- **Streak, daily goal, AI limit** use the student's own day (`users.timezone`, default
  Asia/Kolkata).
- **Resources and AI help never change estimates.** Only answers do.

## Machine learning

- **Maths model:** DKT-Q, an LSTM over (skill, response) and (question, response) embeddings plus
  the previous attempt's hints, answer reveal and time gap, with a per-question difficulty bias,
  trained in `ml/notebooks/02_foundationalassist_knowledge_tracing.ipynb`. Test AUC **0.812**,
  accuracy 0.749 on held-out students. Plain DKT (AUC 0.773) can be served with `KT_MODEL=dkt`.
- **Serving:** `.npz` weights + `kt_meta.json`, NumPy forward pass in `backend/app/ml/dkt.py`
  (parity with PyTorch checked at export). Loaded once at startup, never trained by the app. Within
  one request the student's model state is computed once and reused (cache on the DB session,
  keyed by the history), not across requests.
- **Where the model is used:** the adaptive diagnostic (most informative question, p(1−p)),
  practice question choice, ordering untested skills, and a second opinion in the diagnosis.
- **Live monitoring** (admin, per subject): predictions are stored before each answer, so AUC, log
  loss, Brier score and calibration on real students are honest out-of-sample numbers.

## AI tutor (`ai.py`, `llm.py`)

- OpenRouter, free models, tried in order: `nvidia/nemotron-3-ultra-550b-a55b:free`,
  `google/gemma-4-31b-it:free`, `google/gemma-4-26b-a4b-it:free`, `openrouter/free`
  (`AI_MODEL`, `AI_FALLBACK_MODELS`). The model that answered last is tried first for 5 minutes.
  Local probe on 2026-11-13 (hint prompt, the app's own client): nemotron answered in 12.0 s,
  both gemma models returned 429 (rate-limited upstream), `openrouter/free` answered in 3.2 s.
- Reasoning is requested short and hidden (`effort: low`); a model that rejects that field is
  asked again once without it. Hints use up to 600 tokens, explanations 1,500.
- **Time budget:** one request never takes more than `AI_TOTAL_SECONDS` (50 s): each attempt reads
  for at most 25 s and no new model starts with less than 5 s left (Vercel's proxy limit is 120 s).
- **Errors:** 401/403 mean the key is rejected: logged as an ERROR (never the key), remembered for
  10 minutes (`GET /ai/status` → `key_ok: false`, `enabled: false`), no other model tried, and the
  student gets 503 `ai_key_rejected` "The AI tutor isn't available right now.". Busy/time-out →
  503 `ai_unavailable` (retryable). Off → 503 `ai_disabled`. Daily limit → 429 `ai_daily_limit`
  (resets at the student's midnight). `POST /admin/ai/test` runs "Reply with OK" through the chain
  and reports ok / model / latency / error (never the key); a success clears the key flag.
- The key is cleaned of surrounding quotes, spaces and a "Bearer " prefix (a common paste mistake).
- **Explanations** exist only for answered questions; the prompt lists every accepted form and asks
  the model to say so kindly if the student's answer is in fact right. Cached per question and kind
  of answer.
- **AI hints** are checked on the server: any hint containing the answer (value, any accepted
  rounded form, the mixed number, the correct option's text or letter, a map letter as a standalone
  capital) is thrown away and the skill hint is shown with `ai_failed: true`, so the student can try
  again. A hint never fails with a 5xx.
- Every text is labelled AI-generated; admins can hide any text. Only the question, its answer and
  the student's response are sent: no name, email or id. Map questions are described in words
  (the model cannot see the map).

## Deferred (not in v3)

Worked-example fading, self-explanation prompts, confidence ratings, per-student target success
tuning, free click-anywhere map answers, the 19 ordering questions whose order can't be recovered,
World/Asia/India maps, model-state caching across requests, a light theme, DBE-KT22.

## What is original, mocked or limited (honest list)

- **Concept notes and worked examples** are original MENTORX content written with AI assistance
  (`seeddata/resources*.yaml`, labelled "AI-assisted, pending teacher review"). A teacher review
  is still to do. Every Maths skill also links to its genuine Common Core standard page.
- **No videos.** Admins can add videos.
- **AI hints and explanations** come from free language models and can be wrong; they are
  labelled and moderated, never used for scoring.
- **Prerequisites** are curated from Common Core grade progressions, never inferred.
- **Images** load from the dataset's own servers (`check_images.py` + a reseed remove broken ones).
- **Thresholds** (mastery, stuck, pace) are first choices from the learning-science literature, not
  tuned on our students yet; tune them after a pilot.
- **Database:** PostgreSQL. Some dataset questions refer to earlier parts of their problem set.
  Six that can't be answered alone are excluded (`seed.NEEDS_EARLIER_PART`, reason
  `needs_earlier_part`), found by a keyword search plus reading each match; the search can't find
  every case, so admins can still switch any question off.
