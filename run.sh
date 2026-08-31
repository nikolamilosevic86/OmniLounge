#!/usr/bin/env bash
# Single-command local dev bootstrap for macOS/Linux: creates .env if
# missing, installs Node + Python dependencies if needed, then starts the
# database, backend, and frontend together (same as `npm run dev`).
#
# Usage: ./run.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -f .env ]; then
  echo "No .env found -- generating one from .env.example (random dev JWT secret, local registration enabled)."
  if command -v python3 >/dev/null 2>&1; then
    python3 scripts/generate_env.py
  else
    python scripts/generate_env.py
  fi
  echo "Edit .env to add real secrets/OAuth2 credentials before deploying anywhere but localhost."
fi

# Activating an existing .venv (if present) puts its python3/pip3 on PATH,
# so the `python3 -m server.main` call inside `npm run dev` picks up the
# right interpreter too -- this script doesn't create a venv itself, it
# only uses one if you've already set one up (matches this repo's existing
# `pip install -r requirements.txt` setup instructions, venv optional).
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [ ! -d node_modules ]; then
  echo "Installing Node dependencies..."
  npm install
fi

echo "Installing Python dependencies..."
pip install -q -r requirements.txt

echo "Starting OmniLaunge (Postgres + backend + frontend)..."
npm run dev
