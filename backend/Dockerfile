# MENTORX API image. Build from the REPOSITORY ROOT (it needs ml/ and question_bank/ too):
#   docker build -f backend/Dockerfile -t mentorx-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Same directory layout as the repository: the backend finds the question bank and the
# model artifacts relative to its own source.
WORKDIR /srv

# Dependencies first (cached unless the package definitions change).
COPY ml/pyproject.toml ml/
COPY ml/mentorx_ml ml/mentorx_ml
COPY backend/pyproject.toml backend/
COPY backend/app backend/app
RUN pip install ./ml && pip install -e ./backend

COPY backend/alembic backend/alembic
COPY backend/alembic.ini backend/
COPY backend/scripts backend/scripts
COPY backend/model_artifacts backend/model_artifacts
COPY question_bank question_bank

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin mentorx \
    && chown -R mentorx /srv
USER mentorx
WORKDIR /srv/backend

ENV ENVIRONMENT=production \
    PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/v1/health', timeout=4)"

CMD ["sh", "scripts/start.sh"]
