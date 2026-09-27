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

echo "==> dbt_utils (several real dbt checks use macros this package ships)"
uv run dbt deps --project-dir dbt_project --profiles-dir qa_tools/dbt_profiles

echo "==> Node dependencies (the dashboard template's own JS suite)"
npm ci

echo "==> Chromium for the real-browser tests"
uv run playwright install --with-deps chromium

echo
echo "Ready. The warehouse is empty until you populate it:"
echo "    uv run mothman pipeline bootstrap"
echo "which generates both collections and runs the real checks (~4 min)."
