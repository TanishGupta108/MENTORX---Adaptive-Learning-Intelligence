# MENTORX — Adaptive Learning Intelligence

**Learn Smarter. Improve Faster.** An AI-powered personal learning mentor for **Mathematics** (grades 6–8, Common Core). A short diagnostic finds what a student already knows. Then a trained deep knowledge-tracing model (DKT-Q, test AUC 0.81) plus transparent rules build a personal plan: skill diagnosis, recommendations with reasons, learning modules, adaptive practice and fresh reassessments, until the student reaches the goal.

**v2 (November 2026):** the adaptive Mathematics tutor on the [FoundationalASSIST](https://huggingface.co/datasets/ASSISTments/FoundationalASSIST) dataset ([module doc](docs/modules/tutor.md)). It answers five questions for every student: what do I understand, what am I struggling with, what next, how should I practise, am I improving? Observed performance and model predictions are always shown separately.

**Earlier milestones (v1, Machine Learning subject):** M0 scaffold ✓ · M1 requirements & design ✓ · M2 question bank ✓ (285 questions, AI-checked, [review log](docs/question-review-log.md)) · M3 data pipeline + EDA ✓ · M4 models ✓ ([ML report](docs/ml-report.md)) · M5 database, auth & core API ✓ · M6 adaptive quiz engine ✓ · M7 learning paths & revision ✓ · M8 frontend MVP ✓ · M9 deployment & hardening ✓ (live at https://mentorx-adaptive-learning-intellige.vercel.app, [deployment guide](docs/deployment.md)) · M10 engagement ✓ (daily goal, streaks, weekly report, feedback; [module doc](docs/modules/engagement.md)) · M11 pilot features ✓, study not yet run ([pilot guide](docs/modules/pilot.md)) · M12 deliverables drafted ([report](docs/report/final-report.md), [testing](docs/report/testing-report.md), [viva Q&A](docs/report/viva-qa.md), [demo script](docs/report/demo-script.md)). See [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) for the feasibility analysis, scope, architecture, database schema, ML methodology and roadmap.

| Part | Stack | Folder |
|---|---|---|
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS v4 · Vitest | [frontend/](frontend/) |
| Backend | FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · PostgreSQL | [backend/](backend/) |
| ML | PyTorch (training) · NumPy (serving) · pandas · scikit-learn · BKT | [ml/](ml/), [backend/app/ml/dkt.py](backend/app/ml/dkt.py) |
| Content | FoundationalASSIST maths questions (seeded, never committed) + curated notes and prerequisites | [backend/app/tutor/seeddata/](backend/app/tutor/seeddata/) |
| UI | Lucide icons · Recharts · dark navy design system | [frontend/src/components/](frontend/src/components/) |

## Local setup

Prerequisites: Git, Python 3.12+ (CI and Render use 3.12), Node.js 22+, PostgreSQL 16+.
No Docker is needed anywhere in this project.

**PostgreSQL**, either:
- the installer from https://www.postgresql.org/download/ (needs admin rights; it runs as a service), or
- without admin rights (how the team laptop is set up): the Windows "zip archive" (binaries) from
  https://www.enterprisedb.com/download-postgresql-binaries, with its `pgsql` folder unzipped to
  `%LOCALAPPDATA%\Programs\pgsql-17`. Then, once, in PowerShell:

  ```powershell
  & "$env:LOCALAPPDATA\Programs\pgsql-17\bin\initdb.exe" -D "$env:LOCALAPPDATA\MENTORX\pgdata" -U postgres -A trust -E UTF8 --locale=C
  ```

  It is not a Windows service, so start it after every restart of the computer:

  ```powershell
  powershell -File backend\scripts\local-db.ps1 start    # also: stop, status
  ```

  (`-A trust` is fine for a development database: it only accepts connections from this computer.)

Then create the role and database the app expects (same as CI):

```bash
psql -h localhost -U postgres -c "CREATE ROLE mentorx LOGIN SUPERUSER PASSWORD 'mentorx'"
psql -h localhost -U postgres -c "CREATE DATABASE mentorx OWNER mentorx"
# (the tests create and reset their own `mentorx_test` database)
```

```bash
# 1. Database: PostgreSQL running on localhost:5432 (above)

# 2. Backend  (http://localhost:8000/docs)
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -e ../ml -e ".[dev]"  # the backend shares the feature code in ml/
copy .env.example .env            # macOS/Linux: cp .env.example .env
alembic upgrade head
python scripts/seed.py           # loads the v1 question bank
python scripts/seed_math.py --data-dir "C:/path/to/FoundationalASSIST"  # Mathematics (needs Problems.csv + Skills.csv)
uvicorn app.main:app --reload

# 3. Frontend  (http://localhost:5173)
cd frontend
npm install
npm run dev                       # proxies /api to the backend on :8000 (no .env needed)

# 4. ML package (training, EDA, reports)
cd ml
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,analysis]"
```

## Checks (the same ones CI runs)

```bash
cd backend  && ruff check . && ruff format --check . && pytest   # needs PostgreSQL running
cd ml       && ruff check . && ruff format --check . && pytest
cd frontend && npm run typecheck && npm test && npm run build
```

CI also installs the API exactly as Render does, starts it in production mode and runs [backend/scripts/smoke.py](backend/scripts/smoke.py) against it.

## Deployment

Vercel (frontend) + Render (API as a native Python service + managed Postgres). The checklist, environment variables and smoke test are in [docs/deployment.md](docs/deployment.md).

## Contributing

- Branch per feature (`feat/quiz-engine`), PR into `main`, at least one review.
- Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- Never commit `.env` files, raw datasets or student data.
- Every number shown in the app or the report must come from real data or a script that was actually run.
