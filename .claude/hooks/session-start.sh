#!/bin/bash
# Bring a fresh container to the state this project's tests and gates
# assume, and say plainly what is still missing.
#
# WHY THIS EXISTS (plans/tooling.md #11, Keith 2026-09-19): every remote
# session starts from a fresh clone with none of the gitignored build
# artifacts, and sessions kept rediscovering the same gaps by reading
# test failures rather than by doing the setup. CLAUDE.md documents all
# of it; documentation is not the same as it being done.
#
# IT DOES NOT POPULATE THE WAREHOUSE, deliberately, and this is the one
# judgement call worth knowing about. `mothman pipeline bootstrap` takes
# minutes over both collections. A session start that blocks that long
# is one people disable, and then none of the rest of this runs either.
# So the hook makes the environment READY and REPORTS whether there is
# data in it, with the command to fix that - a few seconds, every time,
# and nothing surprising happens to a database somebody left in a
# particular state.
set -uo pipefail

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}" || exit 0

say() { printf '  %s\n' "$*"; }

echo "Setting up this checkout..."

# --- PostgreSQL: a SERVER, not a build artifact -----------------------
# The one item on this list that does not survive the container, and the
# one whose absence is most confusing: PostgreSQL reports a missing ROLE
# as "password authentication failed", which reads like a wrong password.
# Hit three times in one session on 2026-09-27 before this existed.
PGUSER_NAME="user"
PGPASS="password"
if command -v pg_isready >/dev/null 2>&1; then
  if ! pg_isready -q 2>/dev/null; then
    sudo -n pg_ctlcluster 16 main start >/dev/null 2>&1 && say "Started the PostgreSQL cluster."
    sleep 2
  fi
  if pg_isready -q 2>/dev/null; then
    if ! sudo -n -u postgres psql -tAc \
        "SELECT 1 FROM pg_roles WHERE rolname='${PGUSER_NAME}'" 2>/dev/null | grep -q 1; then
      sudo -n -u postgres psql -q -c \
        "CREATE ROLE \"${PGUSER_NAME}\" LOGIN SUPERUSER CREATEDB PASSWORD '${PGPASS}';" \
        >/dev/null 2>&1 && say "Created the '${PGUSER_NAME}' role."
    fi
    if ! sudo -n -u postgres psql -tAc \
        "SELECT 1 FROM pg_database WHERE datname='supply'" 2>/dev/null | grep -q 1; then
      sudo -n -u postgres psql -q -c \
        "CREATE DATABASE supply OWNER \"${PGUSER_NAME}\";" \
        >/dev/null 2>&1 && say "Created the 'supply' database."
    fi
    say "PostgreSQL is up."
  else
    say "WARNING: no PostgreSQL. The suite will refuse to start - see CLAUDE.md."
  fi
fi

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export MOTHMAN_SUPPLY_DSN=\"postgresql://${PGUSER_NAME}:${PGPASS}@localhost:5432/supply\""
    echo "export MOTHMAN_TEST_DSN=\"postgresql://${PGUSER_NAME}:${PGPASS}@localhost:5432/postgres\""
  } >> "$CLAUDE_ENV_FILE"
fi

# --- dbt_utils: without it 8 real dbt tests fail ----------------------
if [ ! -d dbt_project/dbt_packages ]; then
  uv run dbt deps --project-dir dbt_project --profiles-dir qa_tools/dbt_profiles \
    >/dev/null 2>&1 && say "Installed dbt_utils." || say "WARNING: dbt deps failed."
else
  say "dbt_utils already installed."
fi

# --- node_modules: without it `npm test` will not start ---------------
if [ ! -d node_modules ]; then
  npm install --no-audit --no-fund >/dev/null 2>&1 && say "Installed node modules." \
    || say "WARNING: npm install failed."
else
  say "Node modules already installed."
fi

# --- Playwright's Chromium -------------------------------------------
# This sandbox ships one that the pinned package does not find on its
# own, so point at it rather than downloading a second copy.
if [ -e /opt/pw-browsers/chromium ]; then
  [ -n "${CLAUDE_ENV_FILE:-}" ] && \
    echo 'export PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium' >> "$CLAUDE_ENV_FILE"
  say "Using the pre-installed Chromium."
else
  uv run playwright install chromium >/dev/null 2>&1 && say "Installed Chromium." \
    || say "WARNING: no Chromium - the e2e module will error."
fi

# --- Is there any data here? ------------------------------------------
STAGED=$(PGPASSWORD="${PGPASS}" psql -h localhost -U "${PGUSER_NAME}" -d supply -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='staging'" 2>/dev/null)
if [ "${STAGED:-0}" -gt 0 ] 2>/dev/null; then
  say "Warehouse has ${STAGED} staged table(s)."
else
  say "Warehouse is EMPTY. Run 'uv run mothman pipeline bootstrap' to populate it"
  say "(a few minutes), or pick it from the 'mothman' menu."
fi

echo "Ready."
exit 0
