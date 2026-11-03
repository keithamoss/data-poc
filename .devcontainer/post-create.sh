#!/usr/bin/env bash
# The one-time setup CLAUDE.md documents for a fresh machine, done once
# here instead (REQ-TEST-095 criterion 8 keeps the written version; this
# is the same list, executed).
#
# NOT the database: docker-compose.yml supplies that, and this script
# deliberately does not start, install or containerise one
# (REQ-TEST-095 criterion 1).
set -euo pipefail

echo "==> Python dependencies"
pip install --no-cache-dir uv
uv sync --dev

echo "==> dbt packages, once per asset (REQ-QAC-368 criterion 4)"
for asset in $(cd assets && ls -d */ | tr -d /); do
  MOTHMAN_ASSET="$asset" uv run mothman env dbt-deps
done

echo "==> Node dependencies (the dashboard template's own JS suite)"
npm ci

echo "==> Chromium for the real-browser tests"
uv run playwright install --with-deps chromium

echo "==> Marking the warehouse as this dev container's (REQ-PIPE-107)"
# Every connection checks the database's recorded identity and refuses one
# with none. MOTHMAN_ENVIRONMENT is `local` here (devcontainer.json).
uv run mothman env mark --confirm local \
  || echo "    Could not mark it - run 'uv run mothman env mark' once the database is up."

echo
echo "Ready. The warehouse is empty until you populate it:"
echo "    uv run mothman pipeline bootstrap"
echo "which generates both collections and runs the real checks (~4 min)."
