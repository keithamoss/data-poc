"""Support for the bootstrap-equivalence test (REQ-TEST-116 criterion 4).

TWO JOBS, both of which have to work in a SPAWNED process as well as in
the test's own, which is why they live in an importable module rather
than in the test file's fixtures:

1. REDIRECT every path a collection pipeline reads or writes on disk -
   the delivery tree, the receipts, the in-flight observations and the
   two results files under reports/ - to the test's own corpus. A
   parallel bootstrap runs each collection in a process spawned by
   `bootstrap._run_concurrently`, and a monkeypatch made in the test
   process does not exist there: a spawned child imports every module
   afresh, so `delivery.DELIVERIES_DIR` would be the REAL data/deliveries
   again. The redirection travels as an environment variable instead,
   which a spawned child does inherit, and is re-applied by
   `redirected_run_collection` on the child's side.

2. SNAPSHOT and COMPARE what a bootstrap recorded - see `snapshot()`.
"""
from __future__ import annotations

import os
from pathlib import Path

#: The environment variable carrying the corpus root into spawned children.
CORPUS_ENV = "MOTHMAN_EQUIV_CORPUS"

from qa_tools.common import bootstrap as _bootstrap  # noqa: E402

#: CAPTURED AT IMPORT, before the test patches `bootstrap._run_collection`
#: to point here - otherwise the in-process (sequential) path would call
#: this wrapper, which would call the patched name, which is this wrapper.
_REAL_RUN_COLLECTION = _bootstrap._run_collection


def apply_redirects(root: Path) -> dict:
    """Point every on-disk input and output of a pipeline run under `root`.

    Returns {(module, attribute): original} so a caller in the test
    process can restore them; a spawned child simply exits.
    """
    from qa_tools.common import delivery, in_flight_log, scenario_map, scripted_decisions
    from qa_tools.tools import results_history

    root = Path(root)
    targets = {
        (delivery, "DELIVERIES_DIR"): root / "deliveries",
        (delivery, "RECEIPTS_DIR"): root / "receipts",
        (delivery, "BOOKKEEPING_PATH"): root / "generator_bookkeeping.json",
        (scenario_map, "PLACEMENTS_PATH"): root / "scenario_placements.json",
        (in_flight_log, "OBSERVATIONS_DIR"): root / "observations" / "in_flight",
        # A CUT-DOWN CORPUS CANNOT CARRY THE REAL SCRIPTS: they name supplies
        # it does not have, and the player refuses rather than finish a
        # history missing one (REQ-GEN-135 criterion 6). Here, not only in
        # run_into_fresh_database, so a SPAWNED collection gets it too - the
        # on-demand equivalence test failed on every run without it.
        (scripted_decisions, "SCRIPT_PATH"): root / "no_scripted_decisions.yaml",
        # run_pipeline() ENDS by writing `<ROOT>/reports/<results_json>`,
        # and the real ones are what the dashboard build and its e2e tests
        # read.
        (results_history, "ROOT"): str(root),
    }
    original = {}
    for (module, name), value in targets.items():
        original[(module, name)] = getattr(module, name)
        setattr(module, name, value)
    return original


def restore(original: dict) -> None:
    for (module, name), value in original.items():
        setattr(module, name, value)


def redirected_run_collection(name: str, sequential: bool,
                              record_deliveries: bool = False, **replay) -> float:
    """`bootstrap._run_collection`, with the corpus redirection applied first.

    The test patches `bootstrap._run_collection` to this in BOTH modes,
    so the sequential reference and the parallel run go through exactly
    the same wrapper - the only difference left between them is the one
    under test. Pickled BY NAME into the spawned child, which is why it
    is a top-level function of an importable module.
    """
    root = os.environ.get(CORPUS_ENV)
    if not root:
        raise RuntimeError(
            f"{CORPUS_ENV} is not set - refusing to run a collection pipeline "
            f"against this repo's real delivery tree")
    apply_redirects(Path(root))
    return _REAL_RUN_COLLECTION(name, sequential, record_deliveries=record_deliveries, **replay)


# --------------------------------------------------------------------------
# What is compared, and what is not.
# --------------------------------------------------------------------------

# THE SNAPSHOT RULES AND CODE LIVE IN qa_tools/common/equivalence.py since
# REQ-TEST-239 (its NFR: only through mothman), so `mothman debug equivalence`
# and these on-demand tests compare by one set of rules.
from qa_tools.common.equivalence import (  # noqa: E402,F401
    CLOCK_COLUMNS, DERIVED_COLUMNS, ORDINAL_COLUMNS, SURROGATE_COLUMNS,
    UNCOMPARABLE_COLUMNS, differences, snapshot, summary)


# --------------------------------------------------------------------------
# One route into a database of its own (tests/test_kept_routes_agree.py,
# tests/test_replay_clock.py).
# --------------------------------------------------------------------------

def fresh_database(name: str) -> str:
    import psycopg
    from conftest import mark_test_database
    admin = os.environ["MOTHMAN_TEST_DSN"]
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')
        mark_test_database(conn, name)
    info = psycopg.conninfo.conninfo_to_dict(admin)
    info["dbname"] = name
    return psycopg.conninfo.make_conninfo(**info)


def drop_database(name: str) -> None:
    import psycopg
    with psycopg.connect(os.environ["MOTHMAN_TEST_DSN"], autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def run_into_fresh_database(tree: Path, db_name: str, run, inspect=None) -> dict:
    """`run()` against a new, empty database with every on-disk path under
    `tree`; that database's snapshot. The database is dropped afterwards."""
    dsn = fresh_database(db_name)
    try:
        return run_into_database(tree, dsn, run, inspect, ensure_schema=True)
    finally:
        drop_database(db_name)


def run_into_database(tree: Path, dsn: str, run, inspect=None, *,
                      ensure_schema: bool = False) -> dict:
    """`run()` against the database at `dsn` - an existing one, such as a
    resume's copy of a checkpoint (REQ-TEST-159) - with every on-disk path
    under `tree`; its snapshot. Scripted decisions are switched off - they
    replay the synthetic scenarios over the whole corpus and refuse a
    cut-down history for missing the rest. `inspect(dsn)`, when given, is
    called and its answer kept under "inspected"."""
    import shutil

    import pytest

    from qa_tools.common import supply_db

    mp = pytest.MonkeyPatch()
    original = apply_redirects(tree)
    scratch = None
    try:
        mp.setenv("MOTHMAN_SUPPLY_DSN", dsn)
        supply_db.release_connections()
        scratch = supply_db.scratch_dir()
        mp.delenv("GITHUB_REPOSITORY", raising=False)
        if ensure_schema:
            with supply_db.connect(label="test-kept-routes") as conn:
                from qa_tools.common import qa_store
                qa_store.ensure_schema(conn)
        run()
        snap = snapshot(dsn)
        if inspect is not None:
            snap["inspected"] = inspect(dsn)
        return snap
    finally:
        supply_db.release_connections()
        mp.undo()
        restore(original)
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
