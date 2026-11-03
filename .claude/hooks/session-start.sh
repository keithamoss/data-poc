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
    PG_UP=1
  else
    say "WARNING: no PostgreSQL. The suite will refuse to start - see CLAUDE.md."
  fi
fi

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export MOTHMAN_SUPPLY_DSN=\"postgresql://${PGUSER_NAME}:${PGPASS}@localhost:5432/supply\""
    echo "export MOTHMAN_TEST_DSN=\"postgresql://${PGUSER_NAME}:${PGPASS}@localhost:5432/postgres\""
    # WHICH DEPLOYMENT THIS IS. Declared in contract/environments.yaml;
    # a session container is 'sandbox'. Set here rather than defaulted
    # in code, because a build that guesses is a build that can be
    # labelled as somewhere it is not.
    echo 'export MOTHMAN_ENVIRONMENT="sandbox"'
    # NO MOTHMAN_ASSET: which data asset a command acts for is the
    # person's choice each time, with no default (REQ-PIPE-363 criterion
    # 1) - there are two since the asset split. Each asset's database is
    # supply_<asset>, created and marked below (REQ-PIPE-343 criterion 7).
  } >> "$CLAUDE_ENV_FILE"
fi

# --- Leftover test databases: tidied, never the supply database --------
# Keith, 2026-10-20: "setup something to automatically tidy up old leftover
# test databases". A tagged test session's databases are never reused, so
# they pile up (about 130 in one sandbox). Only the suite's own names, with
# nobody connected, created over 12 hours ago - a live session's are always
# younger, because it recreates them when it starts.
if [ -n "${PG_UP:-}" ]; then
  tidied=$(MOTHMAN_TEST_DSN="postgresql://${PGUSER_NAME}:${PGPASS}@localhost:5432/postgres" \
    uv run mothman env tidy-test-databases 2>/dev/null | grep -oE '^Dropped [0-9]+' | grep -oE '[0-9]+')
  [ -n "${tidied:-}" ] && [ "$tidied" != "0" ] && say "Dropped ${tidied} leftover test database(s)."
fi

# --- dbt packages: without them the real dbt tests fail ---------------
# Each asset's own dbt project, assets/<asset>/dbt, one process each.
# `mothman env dbt-deps` decides whether they are installed, from dbt's own
# package-lock.yml (REQ-QAC-368 decision 5) - never a folder merely existing.
for asset in $(cd assets && ls -d */ | tr -d /); do
  if out=$(MOTHMAN_ASSET="$asset" uv run mothman env dbt-deps 2>&1); then
    case "$out" in
      *"already installed"*) say "${asset}'s dbt packages already installed." ;;
      *) say "Installed ${asset}'s dbt packages." ;;
    esac
  else
    say "WARNING: dbt deps failed for ${asset}."
  fi
done

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

# --- Is the warehouse marked as this sandbox's? (REQ-PIPE-107) --------
# Every connection checks the database's recorded identity and refuses one
# with none, so the sandbox marks its own - a no-op once it is. A database
# marked as something else is reported, never re-marked: that is a person's
# decision (`mothman env mark` at a terminal).
# ONE DATABASE PER ASSET, supply_<asset> (REQ-PIPE-343 criteria 4 and 7),
# each created if missing and marked for its own asset, one process each.
if [ "${PG_UP:-}" = "1" ]; then
  for asset in $(cd assets && ls -d */ | tr -d /); do
    if ! sudo -n -u postgres psql -tAc \
        "SELECT 1 FROM pg_database WHERE datname='supply_${asset}'" 2>/dev/null | grep -q 1; then
      sudo -n -u postgres psql -q -c \
        "CREATE DATABASE \"supply_${asset}\" OWNER \"${PGUSER_NAME}\";" >/dev/null 2>&1
    fi
    if MOTHMAN_ENVIRONMENT=sandbox MOTHMAN_ASSET="$asset" \
       MOTHMAN_SUPPLY_DSN="postgresql://${PGUSER_NAME}:${PGPASS}@localhost:5432/supply_${asset}" \
       uv run mothman env mark --confirm sandbox >/dev/null 2>&1; then
      say "supply_${asset} is marked as this sandbox's."
    else
      say "WARNING: could not mark supply_${asset} as 'sandbox' - run"
      say "'MOTHMAN_ASSET=${asset} uv run mothman env mark' to see why."
    fi
  done
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

# --- Is the period-table guard installed? (REQ-PIPE-129 criterion 18) ---
# Asked wherever the qa schema exists - not only where tables are staged
# (#113): a guard missing from a built schema is worth saying either way.
HAS_QA=$(PGPASSWORD="${PGPASS}" psql -h localhost -U "${PGUSER_NAME}" -d supply -tAc \
  "SELECT to_regclass('qa.schema_version') IS NOT NULL" 2>/dev/null)
if [ "${HAS_QA}" = "t" ]; then
  GUARDS=$(PGPASSWORD="${PGPASS}" psql -h localhost -U "${PGUSER_NAME}" -d supply -tAc \
    "SELECT count(*) FROM pg_event_trigger WHERE evtname IN ('period_table_guard','period_view_drop_guard') AND evtenabled <> 'D'" 2>/dev/null)
  if [ "${GUARDS:-0}" != "2" ]; then
    say "WARNING: the database guard on period tables is NOT installed; the other two"
    say "guards still run (REQ-PIPE-129). 'uv run mothman supply install-guard' puts it back."
  fi
fi

echo "Ready."
exit 0
