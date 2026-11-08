#!/bin/sh
# Container entrypoint: migrate, load the question bank (idempotent), serve.
set -eu

alembic upgrade head
python scripts/seed.py

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
