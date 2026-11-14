# CLAUDE.md: MENTORX (read this first)

AI-powered adaptive tutor with two subjects: Mathematics (grades 4-8, Common Core,
FoundationalASSIST dataset) and Geography map skills (Slepemapy.cz, `docs/modules/geography.md`),
each with its own trained DKT-Q knowledge-tracing model. The product brief is `build.md`.
The detailed design and the honest list of what is limited are in `docs/modules/tutor.md`.

## Where we are (2026-11-13): v3 DEPLOYED
- `main` = `feat/mentorx-v2-maths-tutor` at the v3 commit, pushed; Render + Vercel run it.
  Multi-subject (Maths + Geography map skills, `docs/modules/geography.md`), Home/Progress pages,
  answer-checking policy + `scripts/regrade.py`, personalization, sturdier LLM chain (`llm.py`).
  Migration `c5e8a1f4b2d7` ran on production.
- Production DB: Geography seeded (16 skills, 930 questions). `regrade.py --dry-run` on production:
  5 answers checked, 0 changed, so it was not applied.
- Live smoke PASSED (v3) incl. Geography. One earlier run timed out (>60 s) on one request just
  after seeding, probably the first Geography model load on the free Render instance; it left one
  smoke-*@example.com account behind.
- Checks (2026-11-14): backend 305 passed, frontend 45 passed, typecheck and build clean.
- 2026-11-14 review fixes: AI calls release their DB connection before calling the model
  (`ai._generate`); `PATCH /profile` uses onboarding's checks (`profile.check_update`);
  site-wide sign-up cap `REGISTRATIONS_GLOBAL_PER_HOUR`.
- Commit 047bc65 (2026-11-14) carries the wrong title ("fix: issues from the project review",
  a copy of 4cf14b5). It actually adds ordering questions, the needs_earlier_part exclusions and
  the UI-check fixes. Not rewritten, to avoid a force push on main.
- Production scripts from the laptop: put the Render External Database URL in `backend/.env.prod`
  (git-ignored) and set it as DATABASE_URL for the script; never print it.

## Hallmark redesign (2026-11-14), DEPLOYED (c24f9b1); live smoke PASSED (v3); refresh_states run on production (3 students, 0 changed)
- `design.md` (root) locks the system: navy, one periwinkle signal (old blue accent removed),
  Bricolage Grotesque on headings only, system body face, hairlines before cards. Tokens in
  `frontend/src/index.css` `@theme` (OKLCH). Landing keeps its own scoped block (`landing.css`).
- Shell is a top bar (`components/AppShell.tsx`), bottom tabs under 60rem; Home leads with the
  one task for today; Diagnosis summary is a figure row; app lint (`sloplint --scope app`) clean.
- Diagnosis rule: from `ANSWERS_DECIDE_AFTER` = 5 answers the model has no veto. After deploying,
  run `scripts/refresh_states.py` on production once (stored statuses are stale until then).
- Local sample student `sam@example.com` exists only in the local DB (landing screenshots).

## Where we were (2026-11-12)
- v2.1 is DEPLOYED (2026-11-12): `main` = `feat/mentorx-v2-maths-tutor`, pushed. Render (API) and
  Vercel (frontend) run it; the production DB is seeded with Mathematics; `OPENROUTER_API_KEY` and
  `ADMIN_EMAILS` are set on Render. Live check: `python backend/scripts/smoke.py
  https://mentorx-adaptive-learning-intellige.vercel.app` (prints PASSED (v2)).
- Pushing to `main` auto-deploys both. Run all the checks before pushing.
- Tests: backend 212 passed, frontend 16 passed; typecheck and build clean.
- Local DB is seeded with the real data: 132 skills, 2,942 single-skill questions, 354 multi-skill
  questions, notes and a worked example for every available skill.
- Untracked user files: `build.md`, two `.ipynb` at the root. Don't commit them unless asked.

## Open items (next work)
1. Teacher review of the AI-assisted notes (`backend/app/tutor/seeddata/resources_grade*.yaml`).
2. Done 2026-11-14: production Maths reseeded (13 ordering questions usable, 6 needs_earlier_part
   exclusions, 132 available skills, 2,950 single-skill questions); live smoke PASSED (v3).
3. Done 2026-11-14 (headless Chrome via playwright-core in the scratchpad, local servers):
   onboarding, placement check, diagnosis trace + predictions, skill notes, practice incl. ordering,
   My mistakes, real AI explain + AI hint, Mixed practice, Geography map check, Progress, Admin
   model monitor all worked. Fixed: multi-line skill hints, cut-off numeric input hint, onboarding
   "Next:" text shown before a goal was chosen.
4. Pilot with real students, then tune the thresholds in `backend/app/core/config.py`.
5. Optional: add the original Kaggle `dkt_best.pth` (194 skills) for comparison; the current
   DKT-Q (AUC 0.812) is better.
6. After content changes, reseed production from the laptop (`docs/deployment.md`, "Mathematics content").

## Layout
- `backend/app/tutor/`: the tutor (v2 Maths, v3 multi-subject).
  - Subjects (codes, credits, per-subject options): `subjects.py`; student's local day: `localtime.py`.
  - Answer checking: `answers.py`, `mathexpr.py` (safe SymPy). Ordering keys: `ordering.py`.
  - Question HTML, images, WIRIS → MathML: `html.py`.
  - Model serving: `kt.py`, with NumPy inference in `app/ml/dkt.py`.
  - Adaptive diagnostic and reassessment: `assess.py`.
  - Skill and Mixed practice: `practice.py`.
  - Diagnosis rules: `state.py`.
  - Recommendations: `recommend.py`.
  - AI tutor: `ai.py`, `llm.py`.
  - Admin and model monitor: `admin.py`.
  - Read models (dashboard, streak, ...): `views.py`.
  - Seeding: `seed.py` (Maths), `seed_geo.py` (Geography). Re-checking old answers: `regrade.py`.
- API: `backend/app/api/v2/tutor.py`. Auth is on `/api/v1/auth`.
- Frontend: `frontend/src/pages/*` (Home, Progress, Skill, Practice, ...), `components/AiTutor.tsx`,
  `components/MapQuestion.tsx`, `components/SubjectSwitcher.tsx`, `components/AdminMonitor.tsx`, `api/tutor.ts`.
  Map outlines: `frontend/public/maps/`.
- ML training: `ml/` and `ml/notebooks/02_foundationalassist_knowledge_tracing.ipynb`.
  Model artifacts: `backend/model_artifacts/foundationalassist/` and `backend/model_artifacts/geography/`.
  Geography: `ml/scripts/build_geography_maps.py`, `ml/scripts/train_geography_kt.py`.

## Commands (Windows; the repo path contains an em dash)
```powershell
powershell -File backend\scripts\local-db.ps1 start      # portable PostgreSQL, not a service
cd backend; .venv\Scripts\activate; uvicorn app.main:app --reload
cd frontend; npm run dev                                   # http://localhost:5173
```
In Git Bash, Node needs: `export PATH="$(cygpath "$LOCALAPPDATA")/Programs/node-v22.23.4-win-x64:$PATH"`

- Checks: `cd backend && .venv/Scripts/ruff check . && .venv/Scripts/ruff format --check . && .venv/Scripts/python -m pytest -q`
  and `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- Reseed: `python scripts/seed_math.py --data-dir "C:/Users/Tanish Gupta/Downloads"`.
  The CSVs (incl. `Interactions.csv`, needed for ordering keys) and `image_check.json` live there.
  Never commit the dataset or any recovered keys (Maths question ids are public dataset ids).
- Image check: `python scripts/check_images.py --data-dir <same folder>`.
- Migrations: `alembic upgrade head`. The latest is `d7a2f9c4e1b3` (ordering answer type).
- Geography reseed: `python scripts/seed_geography.py --data-dir "C:/Users/Tanish Gupta/Downloads/mentorx-new-subject/slepemapy-2015-05-21"`.

## Rules that must hold
- Observed performance and model predictions are always separate fields and labels. A skill
  with no answers is "Needs Assessment", whatever the model says.
- Only single-skill answers count as evidence for a skill (`Interaction.n_skills == 1`). The model
  receives multi-skill questions with all their skills.
- Answer keys never reach the client before an answer. AI explanations exist only for answered
  questions. AI hints pass the leak check in `ai.leaks_answer`.
- Resources and AI help never change estimates; only answers do.
- Never invent URLs, data or metrics. Every number must come from real data or a script that ran.

## Secrets and AI
- `backend/.env` holds `OPENROUTER_API_KEY`. **Never print or commit it.**
- Free models are often rate-limited upstream (429). `AI_FALLBACK_MODELS` handles this
  (nemotron worked in testing).
- Tests force a dummy key and an unreachable URL (`tests/conftest.py`), so they never call the
  real API.

## Working with this user
- Beginner on ops; wants the work done end to end, with exact click-by-click steps for anything
  that needs their accounts.
- Replies in simple Hinglish are welcome.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- When editing files from Python on Windows, write with `newline="\n"`. Heredocs that contain
  apostrophes break in the Bash tool, so put patch scripts in files.
