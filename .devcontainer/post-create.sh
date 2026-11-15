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

echo "==> Marking each asset's warehouse database as this dev container's (REQ-PIPE-107)"
# Every connection checks the database's recorded identity and refuses one
# with none. MOTHMAN_ENVIRONMENT is `local` here (devcontainer.json). ONE
# DATABASE PER ASSET, supply_<asset> (REQ-PIPE-343 criteria 4 and 7), made by
# docker-compose.yml's init script and found by each command from
# MOTHMAN_ASSET on the server devcontainer.json's PGHOST names - no
# MOTHMAN_SUPPLY_DSN (Keith, 2026-11-15). Each marked for its own asset, one
# process each, typing both ids as anyone marking a database does.
for asset in $(cd assets && ls -d */ | tr -d /); do
  MOTHMAN_ASSET="$asset" uv run mothman env mark --confirm "${asset}/local" \
    || echo "    Could not mark supply_${asset} - run 'MOTHMAN_ASSET=${asset} uv run mothman env mark' once it exists."
done

echo
echo "Ready. Each asset's warehouse is empty until you populate it:"
echo "    MOTHMAN_ASSET=<asset> uv run mothman pipeline bootstrap"
echo "which generates that asset's collections and runs the real checks."
