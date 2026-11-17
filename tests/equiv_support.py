"""Support for the tests that compare two runs of today's code in one session:
the kept routes (REQ-PIPE-086 criterion 11) and the replay clock
(REQ-PIPE-081).

TWO JOBS:

1. REDIRECT every path a collection pipeline reads or writes on disk -
   the delivery tree, the receipts, the in-flight observations and the
   two results files under reports/ - to the test's own tree.

2. SNAPSHOT and COMPARE what a run recorded - see `snapshot()`.
"""
from __future__ import annotations

import functools
import json
import os
from collections import Counter
from pathlib import Path

from state_paths import fixed


def apply_redirects(root: Path) -> dict:
    """Point every on-disk input and output of a pipeline run under `root`.

    Returns {(module, attribute): original} so a caller in the test
    process can restore them; a spawned child simply exits.
    """
    from asset_model import delivery as delivery_tree
    from generator import delivery_writer
    from qa_tools.common import in_flight_log, supply_db
    from scenarios import placements as scenario_placements
    from scenarios import scripted_decisions
    from qa_tools.tools import results_history

    root = Path(root)
    targets = {
        (delivery_tree, "default_deliveries_dir"): fixed(root / "deliveries"),
        (delivery_tree, "default_receipts_dir"): fixed(root / "receipts"),
        (delivery_writer, "bookkeeping_path"): fixed(root / "generator_bookkeeping.json"),
        (scenario_placements, "placements_path"): fixed(root / "scenario_placements.json"),
        (in_flight_log, "OBSERVATIONS_DIR"): root / "observations" / "in_flight",
        # A CUT-DOWN CORPUS CANNOT CARRY THE REAL SCRIPTS: they name supplies
        # it does not have, and the player refuses rather than finish a
        # history missing one (REQ-GEN-135 criterion 6). Here, not only in
        # run_into_fresh_database, so a SPAWNED collection gets it too - the
        # on-demand equivalence test failed on every run without it.
        (scripted_decisions, "script_path"): functools.partial(Path, root / "no_scripted_decisions.yaml"),
        # run_pipeline() ENDS by writing `<ROOT>/reports/<results_json>`,
        # and the real ones are what the dashboard build and its e2e tests
        # read.
        (results_history, "reports_root"): fixed(str(root / "reports")),
        # DBT'S TARGETS AND THE STAGING CSVs, which would otherwise sit under
        # the REAL data/dbt_scratch/ for as long as the bootstrap runs - and a
        # module beside this one on the same xdist run (REQ-TEST-252's "nothing
        # is written under the real tree") saw them there (post-build-review
        # #241).
        (supply_db, "scratch_dir"): functools.partial(_corpus_scratch_dir, root,
                                                      supply_db.scratch_dir),
    }
    original = {}
    for (module, name), value in targets.items():
        original[(module, name)] = getattr(module, name)
        setattr(module, name, value)
    return original


def _corpus_scratch_dir(root: Path, real) -> Path:
    """The real scratch directory's own key, under the corpus."""
    return root / "dbt_scratch" / real().name


def restore(original: dict) -> None:
    for (module, name), value in original.items():
        setattr(module, name, value)


# --------------------------------------------------------------------------
# What is compared, and what is not.
# --------------------------------------------------------------------------

# THE SNAPSHOT RULES AND CODE: what a run recorded, normalised so two runs
# of today's code in one test session can be compared row for row - a
# delivery kept three ways (tests/test_kept_routes_agree.py), a replay's
# stamps (tests/test_replay_clock.py). Moved here from the retired
# before-and-after harness, qa_tools/common/equivalence.py (REQ-TEST-393),
# because only tests use it.

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
    # REQ-PIPE-168's verdict rows, stamped like the filing they belong to.
    "verdict": {"recorded_at"},
    # REQ-PIPE-170's applied record, stamped when the person confirmed.
    "correction_applied": {"applied_at"},
    # A confirmed correction's parked moves (Keith, 2026-10-11, (p)).
    "correction_parked": {"parked_at"},
    "correction_parked_resolved": {"resolved_at"},
    # REQ-PIPE-279's attempts: when one began and ended is the wall clock;
    # whether it ended is compared (DERIVED_COLUMNS), as a run's completion is.
    "run_attempt": {"began_at", "ended_at", "elapsed_ms"},
    # REQ-PIPE-323's offset groups: made at the simulated instant plus the
    # wall clock's few microseconds of work, so which groups were made, by
    # which route, is compared and when to the microsecond is not.
    "period_group": {"made_at"},
}

#: SURROGATE IDS WITH NO ORDER WORTH KEEPING, dropped outright. Rows that
#: point at them are compared by what they point AT (DERIVED_COLUMNS).
SURROGATE_COLUMNS = {
    "census": {"id"},
    "filing": {"id"},
    "owed_run": {"id"},
    "verdict": {"id"},
    "correction_applied": {"id"},
    "correction_parked": {"id"},
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
    # REQ-PIPE-266's package-gate applications: one collection's gate is
    # applied in its own order, and two collections replaying side by side
    # interleave the bigserial.
    "gate_application": ("id", ("collection_id",)),
}

#: Columns recomputed as a natural value rather than compared raw.
_LOAD = ("(SELECT lo.dataset_id || '|' || lo.physical || '|' || lo.outcome "
         "FROM qa.load_outcome lo WHERE lo.id = t.{col})")
#: A REFERENCE TO A DECISION is compared as WHICH decision: its collection
#: and its place in that collection's log - the same ordinal the decision's
#: own id becomes (ORDINAL_COLUMNS). Raw ids differ because the two
#: collections replay side by side and interleave; the first self-check
#: found 584 check results, 13 runs, 23 owed runs, 38 decisions and 14
#: decision files differing on that alone. `snapshot` builds the lookup.
_DECISION = "(SELECT r.ref FROM equiv_decision_ref r WHERE r.id = t.{col})"
#: The lookup, as a CTE in the one SELECT that needs it - a snapshot only
#: ever reads.
#: A REFERENCE TO A CHECK RESULT is compared as WHICH result: its run, its
#: tool, its check and its place among that run's results from that tool -
#: the ordinal the result's own id becomes (ORDINAL_COLUMNS). The raw id is
#: a bigserial, new each time a result is recorded again, and interleaves
#: between collections replaying side by side.
_RESULT = "(SELECT r.ref FROM equiv_result_ref r WHERE r.id = t.{col})"
#: A REFERENCE TO A PACKAGE-GATE APPLICATION (REQ-PIPE-266) is compared as
#: WHICH application: its collection and its place in that collection's
#: sequence - the ordinal its own id becomes (ORDINAL_COLUMNS).
_GATE = "(SELECT r.ref FROM equiv_gate_ref r WHERE r.id = t.{col})"
#: The lookups, as CTEs in the one SELECT that needs each - a snapshot only
#: ever reads.
_CTES = {
    "equiv_decision_ref": (
        "SELECT id, collection_id || '#' || row_number() OVER "
        "(PARTITION BY collection_id ORDER BY id) AS ref FROM qa.decision"),
    "equiv_result_ref": (
        "SELECT id, run_key || '|' || tool || '|' || check_id || '|' || row_number() OVER "
        "(PARTITION BY run_key, tool ORDER BY id) AS ref FROM qa.check_result"),
    "equiv_gate_ref": (
        "SELECT id, collection_id || '#' || row_number() OVER "
        "(PARTITION BY collection_id ORDER BY id) AS ref FROM qa.gate_application"),
}
DERIVED_COLUMNS = {
    # A completion stamp is clock time, but WHETHER a run completed is not.
    # A GATE APPLICATION'S START AND END are the replay clock, which runs on
    # with real elapsed time after its anchor (REQ-PIPE-081), so two
    # bootstraps - or a resume and a full replay - stamp them milliseconds
    # apart (CI run 40978105702); whether and how it ended is compared.
    "gate_application": {"started_at": "started_at IS NOT NULL",
                         "ended_at": "ended_at IS NOT NULL"},
    "run": {"completed_at": "completed_at IS NOT NULL",
            "gate_application": _GATE.format(col="gate_application"),
            "caused_by_decision": _DECISION.format(col="caused_by_decision"),
            "caused_by_load": _LOAD.format(col="caused_by_load")},
    "run_attempt": {"began_at": "began_at IS NOT NULL",
                    "ended_at": "ended_at IS NOT NULL",
                    "elapsed_ms": "elapsed_ms IS NOT NULL"},
    # WHAT A RESULT READ, keyed by the result it belongs to.
    "check_read": {"check_result_id": _RESULT.format(col="check_result_id")},
    # Ids pointing at another table's surrogate: compared as what they name.
    # extra carries one too - the decision a re-evaluation came after.
    "check_result": {"load_attempt": _LOAD.format(col="load_attempt"),
                     "extra": "CASE WHEN t.extra ? 'reevaluated_after_decision' THEN "
                              "jsonb_set(t.extra, '{reevaluated_after_decision}', "
                              "coalesce(to_jsonb((SELECT r.ref FROM equiv_decision_ref r "
                              "WHERE r.id::text = t.extra->>'reevaluated_after_decision')), "
                              "'null'::jsonb)) ELSE t.extra END"},
    # refiled_by names the DECISION that re-filed - it was joined to
    # qa.filing until 2026-10-16, comparing an unrelated filing that agreed
    # only when the ids happened to interleave alike.
    "filing": {"refiled_by": _DECISION.format(col="refiled_by")},
    "decision": {"caused_by_decision": _DECISION.format(col="caused_by_decision"),
                 "gate_application": _GATE.format(col="gate_application"),
                 # A RULE-MADE decision's effective time is the replay clock,
                 # which runs on with real elapsed time after its anchor
                 # (REQ-PIPE-081): 29 of 544 differed, by at most 0.69s, between
                 # two bootstraps of one commit, while every person-made and
                 # scripted one matched. Left out for rule decisions only
                 # (Keith, 2026-10-16); their order is still compared, as the
                 # decision log's ordinal.
                 "effective_at": "CASE WHEN t.actor_kind = 'rule' THEN NULL "
                                 "ELSE t.effective_at END"},
    "decision_file": {"decision_id": _DECISION.format(col="decision_id")},
    "census_discrepancy": {"census_id": "(SELECT c.trigger || '|' || coalesce(c.run_key, '') "
                                        "FROM qa.census c WHERE c.id = t.census_id)"},
    "correction_parked_resolved": {
        "decision_id": _DECISION.format(col="decision_id"),
        "parked_id": "(SELECT p.change_reference || '|' || p.dataset_id || '|' || "
                     "p.supply_id || '|' || coalesce(p.from_period, '') || '|' || "
                     "coalesce(p.to_period, '') FROM qa.correction_parked p "
                     "WHERE p.id = t.parked_id)"},
    "owed_run": {"caused_by_decision": _DECISION.format(col="caused_by_decision"),
                 "caused_by_load": _LOAD.format(col="caused_by_load"),
                 "cleared_at": "cleared_at IS NOT NULL",
                 # A knock-on's number (`knock-on/6`, `__r2`) counts those recorded so far,
                 # which differs with the order two collections write in.
                 "run_key": r"regexp_replace(run_key, '(__r|knock-on/)[0-9]+$', '\1#')",
                 "cleared_by_run": r"regexp_replace(cleared_by_run, '(__r|knock-on/)[0-9]+$', "
                                   r"'\1#')"},
    # A verdict names its filing and the verdict it superseded by surrogate
    # id; compare WHICH filing and WHICH verdict (REQ-PIPE-168).
    "verdict": {"filing_id": "(SELECT f.dataset_id || '|' || f.supply_id || '|' || "
                             "coalesce(f.slot, '') || '|' || CASE WHEN f.refiled_by IS NULL THEN 'rule' ELSE 'person' END "
                             "FROM qa.filing f WHERE f.id = t.filing_id)",
                "supersedes": "(SELECT v.dataset_id || '|' || v.supply_id || '|' || "
                              "coalesce(v.classification, '') FROM qa.verdict v "
                              "WHERE v.id = t.supersedes)"},
    "hold": {"resolved_at": "resolved_at IS NOT NULL",
             # resolved_by is a decision's surrogate id; compare WHICH
             # decision resolved it instead.
             "resolved_by": _DECISION.format(col="resolved_by")},
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
    sql = f'SELECT {", ".join(exprs)} FROM qa."{table}" t'
    ctes = [f"{name} AS ({body})" for name, body in _CTES.items() if name in sql]
    if ctes:
        sql = "WITH " + ", ".join(ctes) + " " + sql
    return names, sql


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

    run_seq is compared as drawn.
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
    `tree`; that database's snapshot. The database is dropped afterwards.
    Scripted decisions are switched off - they replay the synthetic
    scenarios over the whole corpus and refuse a cut-down history for
    missing the rest. `inspect(dsn)`, when given, is called and its answer
    kept under "inspected"."""
    import shutil

    import pytest

    from qa_tools.common import supply_db

    dsn = fresh_database(db_name)
    mp = pytest.MonkeyPatch()
    original = apply_redirects(tree)
    scratch = None
    try:
        mp.setenv("MOTHMAN_SUPPLY_DSN", dsn)
        supply_db.release_connections()
        scratch = supply_db.scratch_dir()
        mp.delenv("GITHUB_REPOSITORY", raising=False)
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
        drop_database(db_name)
