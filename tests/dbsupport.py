"""Give a test an EMPTY supply database without destroying anybody else's.

WHAT WENT WRONG, because the fix only makes sense against it. The first
version of this reset the WORKER'S OWN database - dropping every schema -
and that quietly destroyed the data the session-scoped staging fixtures
(bdm_duckdb_dir, cp_duckdb_dir) had loaded once for the whole worker. Any
test file that ran after one of these on the same worker then failed on
missing tables.

It was invisible in the obvious way: running the suite in two halves put
the files on different workers and everything passed, 1973 tests, twice.
Running it whole put a reset-calling file and a staged-data-reading file on
one worker and six tests failed. A green result is about a particular run,
not about the code - which is this project's own standing lesson, met here
by my own harness.

SO EACH SUCH TEST GETS ITS OWN DATABASE, not a cleared version of the
shared one. Dropped and recreated per call, which costs about a tenth of a
second and buys isolation nothing can undo - no ordering rule to remember,
no fixture to depend on in the right order.
"""
from __future__ import annotations

import os

import psycopg

from qa_tools.common import supply_db


def use_empty_supply_db(monkeypatch) -> str:
    """Point this test at an empty database of its own. Returns its DSN.

    Takes `monkeypatch` rather than setting the environment directly so
    the redirection is undone when the test ends - otherwise it would
    leak into every test after it, which is the same class of bug this
    function exists to fix.
    """
    base = os.environ.get(supply_db.SUPPLY_DSN_ENV)
    if not base:
        raise RuntimeError(
            f"{supply_db.SUPPLY_DSN_ENV} is not set - conftest's supply_dsn "
            f"fixture is autouse and should have set it")

    info = psycopg.conninfo.conninfo_to_dict(base)
    scratch = f"{info['dbname']}_scratch"

    # Connected to the worker's own database in order to create the
    # scratch one: PostgreSQL will not let a session create the database
    # it is connected to, so this needs somewhere else to stand.
    with psycopg.connect(base, autocommit=True) as conn:
        # FORCE, because a previous test's leaked connection would
        # otherwise block the drop and fail this test for something it
        # did not do.
        conn.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{scratch}"')
        # Reap a QA tool's connection left idle in a transaction - see
        # conftest's own note for the real incident behind this.
        conn.execute(f'ALTER DATABASE "{scratch}" '
                     "SET idle_in_transaction_session_timeout = '15s'")

    info["dbname"] = scratch
    dsn = psycopg.conninfo.make_conninfo(**info)
    monkeypatch.setenv(supply_db.SUPPLY_DSN_ENV, dsn)
    return dsn
