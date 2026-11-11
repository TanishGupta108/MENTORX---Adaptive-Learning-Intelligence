#!/bin/sh
# Server start (Render's start command, and CI's end-to-end job):
# migrate, load the question bank (idempotent), serve. Run from backend/.
set -eu

alembic upgrade head
python scripts/seed.py
# Mathematics (FoundationalASSIST): the CSVs are licensed and never committed. If the server
# has them (MATH_DATA_DIR), refresh the content on start; otherwise seed once from a laptop
# (docs/deployment.md, "Mathematics content").
if [ -n "${MATH_DATA_DIR:-}" ] && [ -f "${MATH_DATA_DIR}/Problems.csv" ]; then
  python scripts/seed_math.py --data-dir "$MATH_DATA_DIR"
fi

# One worker: the login/registration rate limiters and the model cache live in memory
# (see app/core/rate_limit.py). Scale with a shared store before adding workers.
# --proxy-headers: the platform's proxy sets X-Forwarded-For, which the rate limits use.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}" \
  --no-server-header \
  --no-access-log  # the app logs each request itself, with its request ID (app/core/errors.py)
