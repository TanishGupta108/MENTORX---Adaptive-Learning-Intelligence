# CLAUDE.md: MENTORX (read this first)

AI-powered adaptive Mathematics tutor (grades 4-8, Common Core) on the FoundationalASSIST
dataset with a trained DKT-Q knowledge-tracing model. The product brief is `build.md`.
The detailed design and the honest list of what is limited are in `docs/modules/tutor.md`.

## Where we are (2026-11-12)
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
2. Ordering questions (32) are still excluded: options contain ", ", so they can't be split safely.
3. Check the UI in a browser: diagnosis trace, AI hint/explain, Mixed practice, Admin → Model monitor.
4. Pilot with real students, then tune the thresholds in `backend/app/core/config.py`.
5. Optional: add the original Kaggle `dkt_best.pth` (194 skills) for comparison; the current
   DKT-Q (AUC 0.812) is better.
6. After content changes, reseed production from the laptop (`docs/deployment.md`, "Mathematics content").

## Layout
- `backend/app/tutor/`: v2 tutor.
  - Answer checking: `answers.py`, `mathexpr.py` (safe SymPy).
  - Question HTML, images, WIRIS → MathML: `html.py`.
  - Model serving: `kt.py`, with NumPy inference in `app/ml/dkt.py`.
  - Adaptive diagnostic and reassessment: `assess.py`.
  - Skill and Mixed practice: `practice.py`.
  - Diagnosis rules: `state.py`.
  - Recommendations: `recommend.py`.
  - AI tutor: `ai.py`, `llm.py`.
  - Admin and model monitor: `admin.py`.
  - Read models (dashboard, streak, ...): `views.py`.
  - Seeding: `seed.py`.
- API: `backend/app/api/v2/tutor.py`. Auth is on `/api/v1/auth`.
- Frontend: `frontend/src/pages/*`, `components/AiTutor.tsx`, `components/AdminMonitor.tsx`, `api/tutor.ts`.
- ML training: `ml/` and `ml/notebooks/02_foundationalassist_knowledge_tracing.ipynb`.
  Model artifacts: `backend/model_artifacts/foundationalassist/`.

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
  The CSVs and `image_check.json` live there. Never commit the dataset.
- Image check: `python scripts/check_images.py --data-dir <same folder>`.
- Migrations: `alembic upgrade head`. The latest is `3a3323760dc2`.

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
