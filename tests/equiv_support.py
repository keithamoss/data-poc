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

import json
import os
from collections import Counter
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
    from qa_tools.bdm import orchestrate_bdm
    from qa_tools.common import delivery, in_flight_log, scenario_map, scripted_decisions
    from qa_tools.cp import orchestrate_cp

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
        # run_pipeline()/run_pipeline_cp() END by writing these, and the
        # real ones are what the dashboard build and its e2e tests read.
        (orchestrate_bdm, "RESULTS_PATH"): str(root / "reports" / "results_bdm.json"),
        (orchestrate_cp, "RESULTS_PATH"): str(root / "reports" / "results_cp.json"),
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

#: COLUMNS LEFT OUT, every one named, each for one reason: it is stamped
#: from the wall clock when the row is written, so two bootstraps minutes
#: apart cannot agree on it. A column not listed here IS compared - so a
#: column added to the qa schema later is compared by default, which is
#: the safe direction.
CLOCK_COLUMNS = {
    "run": {"run_timestamp", "run_instant", "created_at", "completed_at"},
    "decision": {"recorded_at"},
    "delivery": {"recorded_at"},
    "filing": {"recorded_at"},
    "load_outcome": {"recorded_at"},
    "period": {"opened_at"},
    "hold": {"raised_at", "resolved_at"},
    # Added 2026-10-06 (REQ-TEST-159), for tables and columns that arrived
    # after this list was written and had been explained by hand in every
    # full-bootstrap comparison since: the census, the identity row's mark,
    # an owed run's own stamps.
    "census": {"taken_at"},
    "identity": {"marked_at"},
    "owed_run": {"owed_at"},
}

#: SURROGATE IDS WITH NO ORDER WORTH KEEPING, dropped outright. Rows that
#: point at them are compared by what they point AT (DERIVED_COLUMNS).
SURROGATE_COLUMNS = {
    "census": {"id"},
    "filing": {"id"},
    "owed_run": {"id"},
}

#: SURROGATE KEYS, replaced rather than dropped. A bigserial id differs
#: between modes because the two collections' rows interleave when they
#: run side by side - but the ORDER WITHIN the partition named here is
#: part of the history (a collection's decision log is a sequence; one
#: tool's results within a run are written in its own order) and must
#: match. So the id is replaced by the row's ordinal within that
#: partition. NOT partitioned by run alone for check_result: with dbt
#: beside the other tools, which tool's results land first in a run is
#: exactly the thing that legitimately changes.
ORDINAL_COLUMNS = {
    "check_result": ("id", ("run_key", "tool")),
    "decision": ("id", ("collection_id",)),
    "load_outcome": ("id", ("dataset_id",)),
}

#: Columns recomputed as a natural value rather than compared raw.
_LOAD = ("(SELECT lo.dataset_id || '|' || lo.physical || '|' || lo.outcome "
         "FROM qa.load_outcome lo WHERE lo.id = t.{col})")
_DECISION = ("(SELECT d.dataset_id || '|' || d.action || '|' || coalesce(d.supply, '') "
             "|| '|' || d.effective_at::text FROM qa.decision d WHERE d.id = t.{col})")

DERIVED_COLUMNS = {
    # A completion stamp is clock time, but WHETHER a run completed is not.
    "run": {"completed_at": "completed_at IS NOT NULL"},
    # Ids pointing at another table's surrogate: compared as what they name.
    "check_result": {"load_attempt": _LOAD.format(col="load_attempt")},
    "filing": {"refiled_by": "(SELECT f.dataset_id || '|' || f.supply_id || '|' || "
                             "coalesce(f.slot, '') FROM qa.filing f WHERE f.id = t.refiled_by)"},
    "owed_run": {"caused_by_decision": _DECISION.format(col="caused_by_decision"),
                 "caused_by_load": _LOAD.format(col="caused_by_load"),
                 "cleared_at": "cleared_at IS NOT NULL",
                 # A knock-on's number (`knock-on/6`, `__r2`) counts those recorded so far,
                 # which differs with the order two collections write in.
                 "run_key": r"regexp_replace(run_key, '(__r|knock-on/)[0-9]+$', '\1#')",
                 "cleared_by_run": r"regexp_replace(cleared_by_run, '(__r|knock-on/)[0-9]+$', "
                                   r"'\1#')"},
    "hold": {"resolved_at": "resolved_at IS NOT NULL",
             # resolved_by is a decision's surrogate id; compare WHICH
             # decision resolved it instead.
             "resolved_by": "(SELECT d.dataset_id || '|' || d.action || '|' || "
                            "coalesce(d.supply, '') || '|' || d.effective_at::text "
                            "FROM qa.decision d WHERE d.id = t.resolved_by)"},
}

#: WHOLE COLUMNS LEFT OUT FOR A REASON OTHER THAN THE CLOCK - one, and its
#: reason measured rather than assumed. tool_output.raw_output is each
#: tool's own unmodified output, and over the full corpus (2026-10-03's
#: two real bootstraps) 464 of 627 differed: dbt's invocation ids,
#: timings and per-run target paths, Soda's scan timestamps, log indices
#: and metric ordering, datacontract-cli's run ids, and Evidently PSI
#: values differing in the last floating-point digit. Every verdict the
#: system acts on is parsed out of it into check_result, which IS
#: compared in full. The row's presence is still compared.
UNCOMPARABLE_COLUMNS = {
    "tool_output": {"raw_output"},
}


def _cols(conn, table: str) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'qa' AND table_name = %s ORDER BY ordinal_position",
        [table]).fetchall()]


def _qa_select(conn, table: str) -> tuple[list[str], str]:
    names, exprs = [], []
    for col in _cols(conn, table):
        if col in UNCOMPARABLE_COLUMNS.get(table, ()):
            continue
        derived = DERIVED_COLUMNS.get(table, {}).get(col)
        if derived:
            names.append(col + "*")
            exprs.append(derived)
            continue
        if col in CLOCK_COLUMNS.get(table, ()) or col in SURROGATE_COLUMNS.get(table, ()):
            continue
        ordinal = ORDINAL_COLUMNS.get(table)
        if ordinal and ordinal[0] == col:
            names.append(f"{col}#within({','.join(ordinal[1])})")
            exprs.append(f"row_number() OVER (PARTITION BY {', '.join(ordinal[1])} "
                         f"ORDER BY {col})")
            continue
        names.append(col)
        exprs.append(f't."{col}"')
    return names, f'SELECT {", ".join(exprs)} FROM qa."{table}" t'


def _canon(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def snapshot(dsn: str) -> dict:
    """Everything a bootstrap recorded, normalised to be comparable.

    - every BASE TABLE in the `qa` schema, every row, every column except
      the ones named above - as a multiset of rows;
    - every table in every OTHER schema (staging, rejected, each period's
      own) by name, row count and a digest of its sorted rows - the
      supply rows themselves, so a supply promoted into a different
      period, or staged differently, shows;
    - the list of schemas, so a per-run schema one mode leaves behind
      shows too.
    """
    import psycopg

    snap: dict = {}
    with psycopg.connect(dsn) as conn:
        qa_tables = [r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'qa' AND table_type = 'BASE TABLE' ORDER BY 1")]
        for table in qa_tables:
            names, sql = _qa_select(conn, table)
            rows = Counter(tuple(_canon(v) for v in r) for r in conn.execute(sql))
            snap[f"qa.{table}"] = (tuple(names), rows)

        schemas = [r[0] for r in conn.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg\\_%' "
            "AND nspname NOT IN ('information_schema', 'public', 'qa') ORDER BY 1")]
        snap["schemas"] = (("schema",), Counter((s,) for s in schemas))
        supply = Counter()
        for schema, table in conn.execute(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_schema = ANY(%s) AND table_type = 'BASE TABLE'",
                [schemas]).fetchall():
            count, digest = conn.execute(
                f'SELECT count(*), md5(coalesce(string_agg(t::text, E\'\\n\' '
                f'ORDER BY t::text), \'\')) FROM "{schema}"."{table}" t').fetchone()
            supply[(f"{schema}.{table}", str(count), digest)] += 1
        snap["supply_tables"] = (("table", "rows", "md5"), supply)
    return snap


def differences(a: dict, b: dict, limit: int = 5) -> list[str]:
    """Human-readable differences between two snapshots; empty when equal."""
    out = []
    for key in sorted(set(a) | set(b)):
        if key not in a or key not in b:
            out.append(f"{key}: present only in {'A' if key in a else 'B'}")
            continue
        (cols_a, rows_a), (cols_b, rows_b) = a[key], b[key]
        if cols_a != cols_b:
            out.append(f"{key}: columns differ {cols_a} vs {cols_b}")
            continue
        only_a, only_b = rows_a - rows_b, rows_b - rows_a
        if not only_a and not only_b:
            continue
        out.append(f"{key}: {sum(rows_a.values())} vs {sum(rows_b.values())} rows; "
                   f"{sum(only_a.values())} only in A, {sum(only_b.values())} only in B")
        for label, extra in (("A", only_a), ("B", only_b)):
            for row in list(extra)[:limit]:
                out.append(f"   only in {label}: " + ", ".join(
                    f"{c}={v}" for c, v in zip(cols_a, row))[:400])
    return out


def summary(snap: dict) -> dict[str, int]:
    return {k: sum(rows.values()) for k, (_c, rows) in snap.items()}


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
