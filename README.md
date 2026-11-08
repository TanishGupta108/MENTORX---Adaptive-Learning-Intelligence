# MENTORX — Adaptive Learning Intelligence

An ML-powered adaptive learning platform that teaches **Machine Learning**. It estimates each student's concept mastery from their real attempts, then uses those predictions to choose the next question, build a learning path and schedule revision.

**Status:** M0 scaffold ✓ · M1 requirements & design ✓ · M2 question bank drafted (285 questions, awaiting review) · M3 data pipeline + EDA ✓ · M4 models ✓ ([ML report](docs/ml-report.md)) · M5 database, auth & core API ✓ · M6 adaptive quiz engine ✓ · M7 learning paths & revision ✓. See [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) for the feasibility analysis, scope, architecture, database schema, ML methodology and roadmap.

| Part | Stack | Folder |
|---|---|---|
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS v4 · Vitest | [frontend/](frontend/) |
| Backend | FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · PostgreSQL | [backend/](backend/) |
| ML | pandas · scikit-learn · XGBoost · BKT | [ml/](ml/) |
| Content | YAML question bank + prerequisite graph | [question_bank/](question_bank/) |

## Local setup

Prerequisites: Git, Python 3.11+ (CI uses 3.12), Node.js 22+, Docker Desktop.

```bash
# 1. Database
docker compose up -d db

# 2. Backend  (http://localhost:8000/docs)
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -e ../ml -e ".[dev]"  # the backend shares the feature code in ml/
copy .env.example .env            # macOS/Linux: cp .env.example .env
alembic upgrade head
python scripts/seed.py           # loads the question bank
uvicorn app.main:app --reload

# 3. Frontend  (http://localhost:5173)
cd frontend
npm install
copy .env.example .env
npm run dev

# 4. ML package (training, EDA, reports)
cd ml
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,analysis]"
```

## Checks (the same ones CI runs)

```bash
cd backend  && ruff check . && ruff format --check . && pytest   # needs the docker Postgres running
cd ml       && ruff check . && ruff format --check . && pytest
cd frontend && npm run typecheck && npm test && npm run build
```

## Contributing

- Branch per feature (`feat/quiz-engine`), PR into `main`, at least one review.
- Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- Never commit `.env` files, raw datasets or student data.
- Every number shown in the app or the report must come from real data or a script that was actually run.
