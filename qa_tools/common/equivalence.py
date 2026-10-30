"""Before-and-after equivalence: capture a commit, compare two captures
(REQ-TEST-239, the lean harness Keith signed 2026-10-16).

WHY. Item 6 merges two near-copies of the per-collection code into one
shared module per tool, and its first call is "byte-identical first,
behaviour later". The test suite checks the behaviours it was written to
check; it does not promise everything else stayed the same. A capture
turns "nothing changed" from an assertion into a diff.

WHAT A CAPTURE IS. The commit checked out into a git worktree of its own,
its own `mothman pipeline bootstrap` run from empty into a scratch
database named for the label, its own results and dashboard build, and
four surfaces recorded into one baseline file:

  S1 recorded-results  every row of every base table in the qa schema,
                       under the clock, surrogate, ordinal and derived
                       rules below - a column added later is compared by
                       default;
  S4 generated-files   the path and sha256 of every file the generators
                       wrote: deliveries, receipts, bookkeeping, placements;
  S5 reports           every results and dashboard JSON under reports/,
                       parsed, with only generated_at removed;
  S7 help-and-menus    every mothman group's and command's --help, and the
                       TUI's menu screens, with COLUMNS fixed and NO_COLOR=1.

NOTHING OF THE CODE UNDER CAPTURE IS PATCHED: it runs as its own process
tree with its own working directory, against the main checkout's Python
environment (NFR: reuse the environment rather than install per capture).

BASELINES ARE STATE, NOT CONFIGURATION: they live under
MOTHMAN_EQUIV_DIR (default: the system temp directory), never in the repo.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: Bumped when what a capture records changes; `compare` refuses two
#: baselines that disagree (criterion 2), because their differences would
#: be the harness's rather than the code's.
HARNESS_VERSION = 2
#: Bumped when a normalising rule below changes, for the same reason.
#: 2 (2026-10-16): the rules the first self-check proved missing - decision
#: references, rule-made decision times, S5's ids and clock instants.
#: 3 (2026-10-24): REQ-PIPE-279's records - an attempt's clock, a read by
#: the result it belongs to, opening order within each collection.
NORMALISER_VERSION = 3

#: THE INSTANT EVERY CAPTURE'S BOOTSTRAP AND BUILD TAKE AS "NOW" (criterion
#: 17, Keith 2026-10-16). A build works out from now which slots have closed
#: and what is still awaiting; the first self-check's two builds, 54 minutes
#: apart, straddled a 10:00 closing and disagreed. Changing this constant
#: makes every earlier baseline incomparable - compare refuses the pair.
PINNED_NOW = "2026-10-16T12:00:00+08:00"

#: (code, name, what it holds) - the four surfaces of the lean harness.
SURFACES = (
    ("S1", "recorded-results", "every row of every qa table, normalised"),
    ("S4", "generated-files", "path and sha256 of every generated file"),
    ("S5", "reports", "every results and dashboard JSON, generated_at removed"),
    ("S7", "help-and-menus", "every --help text and the TUI's menu screens"),
)
_BY_NAME = {name: code for code, name, _ in SURFACES}
_CODES = {code for code, _, _ in SURFACES}

#: S5's KEYS LEFT OUT, each a clock stamp: the build's own time, a run's
#: wall-clock timestamp (CLOCK_COLUMNS' run_timestamp), and a decision's
#: recorded_at (CLOCK_COLUMNS' decision.recorded_at) - 5,280 run stamps and
#: 235 recordedAt values differed between the first self-check's two builds.
REPORT_KEYS_REMOVED = ("generated_at", "run_timestamp", "recordedAt")
#: S7: the terminal every help text and menu screen is rendered at.
COLUMNS, ROWS = 100, 40


class Refused(RuntimeError):
    """A capture or compare that must not go ahead - said, never worked round."""


class StageFailed(RuntimeError):
    def __init__(self, stage: str, detail: str):
        super().__init__(f"capture failed at stage '{stage}': {detail}")
        self.stage = stage


def surface_codes(given: tuple[str, ...] | list[str] | None) -> list[str]:
    """Surfaces by code or by name (criterion 3); all four when none given."""
    if not given:
        return [code for code, _, _ in SURFACES]
    out = []
    for g in given:
        code = g.upper() if g.upper() in _CODES else _BY_NAME.get(g.lower())
        if code is None:
            raise Refused(f"no surface {g!r} - one of " + ", ".join(
                f"{c} ({n})" for c, n, _ in SURFACES))
        out.append(code)
    return out


# ---- S1: the recorded results ----------------------------------------

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
    "run_attempt": {"began_at", "ended_at"},
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
#: OPENING ORDER (REQ-PIPE-279's run_seq) as a run's place among its own
#: collection's runs. Collections replaying side by side draw from one
#: sequence, so the raw numbers interleave differently from one bootstrap to
#: the next while each collection's own order does not - which is the order
#: compared. An attempt's run_seq is placed the same way, by its run's
#: collection. Applied only by snapshot(run_seq_within_collection=True);
#: otherwise the raw numbers are compared.
_RUN_RANK = "(SELECT r.rank FROM equiv_run_rank r WHERE r.run_seq = t.run_seq)"
#: A REFERENCE TO A PACKAGE-GATE APPLICATION (REQ-PIPE-266) is compared as
#: WHICH application: its collection and its place in that collection's
#: sequence - the ordinal its own id becomes (ORDINAL_COLUMNS).
_GATE = "(SELECT r.ref FROM equiv_gate_ref r WHERE r.id = t.{col})"
_ATTEMPT_RANK = ("(SELECT r.rank FROM equiv_attempt_rank r "
                 "WHERE r.run_key = t.run_key AND r.run_seq = t.run_seq)")
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
    "equiv_run_rank": (
        "SELECT run_seq, row_number() OVER (PARTITION BY collection_id ORDER BY run_seq) "
        "AS rank FROM qa.run WHERE run_seq IS NOT NULL"),
    "equiv_attempt_rank": (
        "SELECT a.run_key, a.run_seq, row_number() OVER (PARTITION BY r.collection_id "
        "ORDER BY a.run_seq) AS rank FROM qa.run_attempt a LEFT JOIN qa.run r "
        "ON r.run_key = a.run_key"),
}
#: The derived columns that are opening order, derived only under
#: snapshot(run_seq_within_collection=True).
_OPENING_ORDER = {("run", "run_seq"), ("run_attempt", "run_seq")}

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
            "caused_by_load": _LOAD.format(col="caused_by_load"),
            "run_seq": _RUN_RANK},
    "run_attempt": {"began_at": "began_at IS NOT NULL",
                    "ended_at": "ended_at IS NOT NULL",
                    "run_seq": _ATTEMPT_RANK},
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


def _qa_select(conn, table: str, run_seq_within_collection: bool = False) -> tuple[list[str], str]:
    names, exprs = [], []
    for col in _cols(conn, table):
        if col in UNCOMPARABLE_COLUMNS.get(table, ()):
            continue
        derived = DERIVED_COLUMNS.get(table, {}).get(col)
        if not run_seq_within_collection and (table, col) in _OPENING_ORDER:
            derived = None
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


def snapshot(dsn: str, *, run_seq_within_collection: bool = False) -> dict:
    """Everything a bootstrap recorded, normalised to be comparable.

    - every BASE TABLE in the `qa` schema, every row, every column except
      the ones named above - as a multiset of rows;
    - every table in every OTHER schema (staging, rejected, each period's
      own) by name, row count and a digest of its sorted rows - the
      supply rows themselves, so a supply promoted into a different
      period, or staged differently, shows;
    - the list of schemas, so a per-run schema one mode leaves behind
      shows too.

    run_seq is compared as drawn unless `run_seq_within_collection`, which
    compares each run's place among its own collection's runs instead - for
    two histories whose collections may have been opened side by side in
    different interleavings: a parallel bootstrap against a sequential one,
    or two captures of a parallel bootstrap. A resume against its full
    replay opens one collection in one order, so it compares the raw
    numbers.
    """
    import psycopg

    snap: dict = {}
    with psycopg.connect(dsn) as conn:
        qa_tables = [r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'qa' AND table_type = 'BASE TABLE' ORDER BY 1")]
        for table in qa_tables:
            names, sql = _qa_select(conn, table, run_seq_within_collection)
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




# ---- the other surfaces -----------------------------------------------

#: Under data/, what is NOT generated: dbt's own per-run working
#: directories (supply_db.dbt_target_path), which a run tidies away.
NOT_GENERATED = ("dbt_scratch",)


def generated_files(tree: Path) -> dict[str, str]:
    """S4: every file the bootstrap left under `tree`'s data/ - every
    delivery, every receipt, and the generators' own records - except
    dbt's scratch. Named by WHERE it is rather than file by file, so this
    module never names the generator's bookkeeping, which no QA module may
    (REQ-GEN-043 criterion 7, tests/test_arrivals.py)."""
    data = tree / "data"
    out = {}
    if not data.is_dir():
        return out
    for f in sorted(data.rglob("*")):
        rel = f.relative_to(data)
        if f.is_file() and rel.parts[0] not in NOT_GENERATED:
            out[str(f.relative_to(tree))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


#: S5 KEYS HOLDING A SURROGATE ID, compared as what the id names - the same
#: rule S1 applies (normaliser 2). The first self-check found 1,800
#: decision ids and 936 load-attempt ids differing on interleaving alone.
DECISION_ID_KEYS = ("decision_id", "decisionId", "reevaluated_after_decision")
LOAD_ID_KEYS = ("attempt",)
_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def report_context(dsn: str) -> dict:
    """What S5 needs from the database the build read: each raw decision and
    load-attempt id's comparable name, and every INSTANT that came from a
    clock (CLOCK_COLUMNS) or from a rule-made decision's running replay
    clock - each of which S5 shows as what it is, not as its value."""
    import psycopg

    ctx: dict = {"decisions": {}, "loads": {}, "instants": {}}
    with psycopg.connect(dsn) as conn:
        for raw, ref, rule, at in conn.execute(
                "SELECT id, collection_id || '#' || row_number() OVER "
                "(PARTITION BY collection_id ORDER BY id), actor_kind = 'rule', effective_at "
                "FROM qa.decision"):
            ctx["decisions"][str(raw)] = ref
            if rule:
                ctx["instants"][at] = "<rule-made decision's time>"
        for raw, ref in conn.execute(
                "SELECT id, dataset_id || '#' || row_number() OVER "
                "(PARTITION BY dataset_id ORDER BY id) FROM qa.load_outcome"):
            ctx["loads"][str(raw)] = ref
        tables = {r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'qa'")}
        for table, cols in CLOCK_COLUMNS.items():
            if table not in tables:
                continue
            for col in cols:
                found = conn.execute(
                    "SELECT 1 FROM information_schema.columns WHERE table_schema = 'qa' "
                    "AND table_name = %s AND column_name = %s", [table, col]).fetchone()
                if not found:
                    continue
                for (at,) in conn.execute(
                        f'SELECT DISTINCT "{col}" FROM qa."{table}" WHERE "{col}" IS NOT NULL'):
                    if isinstance(at, datetime):
                        ctx["instants"].setdefault(at, "<clock>")
    return ctx


def _as_instant(value: str):
    if not _INSTANT.match(value):
        return None
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        return None
    return at if at.tzinfo is not None else None


def _normalise_report(value, ctx: dict | None, parent: str | None = None):
    if isinstance(value, list):
        return [_normalise_report(v, ctx, parent) for v in value]
    if isinstance(value, str) and ctx:
        at = _as_instant(value)
        if at is not None and at in ctx["instants"]:
            return ctx["instants"][at]
        return value
    if not isinstance(value, dict):
        return value
    out = {}
    for k, v in value.items():
        if k in REPORT_KEYS_REMOVED:
            continue
        if ctx and v is not None and (k in DECISION_ID_KEYS or (k == "id" and parent == "decisions")):
            out[k] = ctx["decisions"].get(str(v), v)
        elif ctx and v is not None and k in LOAD_ID_KEYS:
            out[k] = ctx["loads"].get(str(v), v)
        else:
            out[k] = _normalise_report(v, ctx, k)
    # A wait measured to a rule-made decision's time is as noisy as that
    # time: left out beside it, kept wherever the arrival still waits (the
    # pinned clock makes that one exact).
    if "waitedSeconds" in out and isinstance(out.get("filledAt"), str) \
            and out["filledAt"].startswith("<"):
        del out["waitedSeconds"]
    return out


def reports(tree: Path, ctx: dict | None = None) -> dict:
    """S5: every JSON the build wrote under `tree`'s reports/, parsed and
    normalised (REPORT_KEYS_REMOVED always; ids and clock instants by
    `report_context` when the database is to hand)."""
    out = {}
    for f in sorted((tree / "reports").glob("*.json")):
        out[f.name] = _normalise_report(json.loads(f.read_text()), ctx)
    return out


_HELP_SCRIPT = r"""
import json, os, sys
import click
from click.testing import CliRunner
from cli.app import cli
out = {}
def walk(cmd, path):
    r = CliRunner().invoke(cli, path + ["--help"], terminal_width=%d,
                           env={"NO_COLOR": "1", "COLUMNS": "%d"})
    out[" ".join(["mothman"] + path)] = r.output
    if isinstance(cmd, click.Group):
        for name in sorted(cmd.list_commands(None)):
            walk(cmd.get_command(None, name), path + [name])
walk(cli, [])
print(json.dumps(out))
""" % (COLUMNS, COLUMNS)

#: The TUI screens captured, each a key sequence from a fresh start: the
#: main menu, and the first screen of each main-menu choice that OPENS A
#: MENU - Quality Assurance, Filing decisions, Calendar and Generate.
#: NEVER a choice that starts work (Process what has arrived, Set up this
#: environment): a capture reads screens, it does not run flows.
MENU_PATHS = {
    "main menu": [],
    "main menu > quality assurance": ["enter"],
    "main menu > filing decisions": ["down", "enter"],
    "main menu > calendar": ["down", "down", "enter"],
    "main menu > generate": ["down", "down", "down", "down", "enter"],
}
_KEYS = {"up": "\x1b[A", "down": "\x1b[B", "enter": "\r"}


def _screen(cmd: list[str], keys: list[str], env: dict, cwd: Path,
            settle: float = 1.5, timeout: float = 30.0) -> str:
    """The visible screen of `cmd` in a real pseudo-terminal after `keys`,
    resolved through a terminal emulator (questionary redraws in place)."""
    import fcntl
    import pty
    import select
    import struct
    import termios

    import pyte

    screen = pyte.Screen(COLUMNS, ROWS)
    stream = pyte.ByteStream(screen)
    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover - the child
        os.chdir(cwd)
        os.execvpe(cmd[0], cmd, env)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLUMNS, 0, 0))

    def pump(wait: float) -> None:
        end = time.monotonic() + wait
        while time.monotonic() < end:
            ready, _, _ = select.select([fd], [], [], 0.1)
            if not ready:
                continue
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                return
            if b"\x1b[6n" in chunk:  # answer the cursor-position request
                y, x = screen.cursor.y + 1, screen.cursor.x + 1
                os.write(fd, f"\x1b[{y};{x}R".encode())
            stream.feed(chunk)
    try:
        pump(min(timeout, 8.0))
        for key in keys:
            os.write(fd, _KEYS.get(key, key).encode())
            pump(settle)
        return "\n".join(line.rstrip() for line in screen.display).rstrip() + "\n"
    finally:
        try:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
        except OSError:
            pass
        os.close(fd)


def help_and_menus(tree: Path, env: dict) -> dict[str, str]:
    """S7: every --help text, then the TUI's menu screens - run by the
    tree's own code."""
    done = subprocess.run([sys.executable, "-c", _HELP_SCRIPT], cwd=tree, env=env,
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise StageFailed("S7", done.stderr[-2000:])
    out = {f"help: {k}": v for k, v in json.loads(done.stdout).items()}
    for label, keys in MENU_PATHS.items():
        out[f"tui: {label}"] = _screen([sys.executable, "-m", "cli.app"], keys, env, tree)
    return out


# ---- capture -----------------------------------------------------------

def baseline_dir() -> Path:
    return Path(os.environ.get("MOTHMAN_EQUIV_DIR")
                or Path(tempfile.gettempdir()) / "mothman-equivalence")


def baseline_path(label: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,40}", label):
        raise Refused(f"label {label!r} must be lower-case letters, digits, - and _ "
                      f"(it names a database and a file)")
    return baseline_dir() / f"{label}.json"


def _scratch_dsn(label: str) -> tuple[str, str, str]:
    """(admin DSN, scratch DSN, database name) on the supply database's own
    server."""
    import psycopg

    supply = os.environ.get("MOTHMAN_SUPPLY_DSN")
    if not supply:
        raise Refused("MOTHMAN_SUPPLY_DSN is not set - a capture needs its server")
    name = f"equiv_{label.replace('-', '_')}"
    info = psycopg.conninfo.conninfo_to_dict(supply)
    admin = psycopg.conninfo.make_conninfo(**{**info, "dbname": "postgres"})
    scratch = psycopg.conninfo.make_conninfo(**{**info, "dbname": name})
    if psycopg.conninfo.conninfo_to_dict(scratch) == info:
        raise Refused(f"{name} is the database MOTHMAN_SUPPLY_DSN names - "
                      f"a capture never writes to the real database")
    return admin, scratch, name


def _commit(ref: str) -> str:
    done = subprocess.run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=ROOT,
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise Refused(f"no commit {ref!r}: {done.stderr.strip()}")
    return done.stdout.strip()


def _timings(output: str) -> dict[str, float]:
    """The bootstrap's own 'Took Birth Registrations 593s, ...' line."""
    m = re.findall(r"Took (.+)", output)
    if not m:
        return {}
    return {name.strip(): float(secs) for name, secs in
            re.findall(r"([^,]+?) (\d+(?:\.\d+)?)s", m[-1])}


def work_dir() -> Path:
    """THE ONE place a capture's worktree lives, whatever its label. Fixed
    rather than per label because the tree's path is printed - `mothman
    population --help` shows a default under it, wrapped to the terminal -
    so a path whose length followed the label made two captures' help
    texts differ (the first self-check, 2026-10-16)."""
    return Path(tempfile.gettempdir()) / "mothman-equivalence-work"


def _one_capture_at_a_time():
    """An exclusive lock for the capture's whole span: one fixed worktree
    means one capture at a time, which also keeps a capture's bootstrap
    timing its own. The operating system releases it if the process dies."""
    import fcntl

    lock = open(Path(tempfile.gettempdir()) / "mothman-equivalence.lock", "w")  # noqa: SIM115
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise Refused("another equivalence capture is running - one at a time, so "
                      "wait for it to finish") from None
    return lock


def _clear_killed() -> None:
    """A KILLED capture never reaches its `finally` (post-build-review #210),
    so its worktree stays registered and its directory on disk; the next
    capture clears them, holding the lock, so never a live one. Its
    database needs nothing here - the database stage drops it by name
    before creating it."""
    work = work_dir()
    if (work / "tree").exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(work / "tree")],
                       cwd=ROOT, capture_output=True)
    shutil.rmtree(work, ignore_errors=True)
    subprocess.run(["git", "worktree", "prune"], cwd=ROOT, capture_output=True)


def capture(ref: str, label: str, *, yes: bool = False, say=print) -> Path:
    """Capture `ref` as `label` (criteria 1, 4, 7-15). Returns the baseline path."""
    import psycopg

    from qa_tools.common import asset_time, environments

    if not asset_time.declared_synthetic():
        raise Refused("this data asset is not declared synthetic - a capture bootstraps "
                      "a synthetic history and is refused on a real asset")
    path = baseline_path(label)
    if path.exists() and not yes:
        raise Refused(f"a baseline called {label!r} exists at {path} - give --yes to "
                      f"replace it")
    admin, scratch, dbname = _scratch_dsn(label)
    commit = _commit(ref)
    env_id = environments.current().id
    work = work_dir()
    tree = work / "tree"
    env = {**os.environ, "MOTHMAN_SUPPLY_DSN": scratch, "PYTHONPATH": str(tree),
           "MOTHMAN_PINNED_NOW": PINNED_NOW,
           "NO_COLOR": "1", "COLUMNS": str(COLUMNS), "TERM": "xterm"}
    env.pop("GITHUB_REPOSITORY", None)
    stage = "worktree"
    baseline: dict = {"harness": HARNESS_VERSION, "normaliser": NORMALISER_VERSION,
                      "label": label, "ref": ref, "commit": commit,
                      "pinned_now": PINNED_NOW,
                      "captured_at": datetime.now(UTC).isoformat(timespec="seconds")}

    def run(stage_name: str, *args: str) -> str:
        done = subprocess.run([sys.executable, "-m", "cli.app", *args], cwd=tree, env=env,
                              capture_output=True, text=True)
        if done.returncode != 0:
            raise StageFailed(stage_name, (done.stdout + done.stderr)[-3000:])
        return done.stdout + done.stderr

    lock = _one_capture_at_a_time()
    try:
        _clear_killed()
        work.mkdir(parents=True)
        subprocess.run(["git", "worktree", "add", "--detach", "-q", str(tree), commit],
                       cwd=ROOT, check=True, capture_output=True)
        packages = ROOT / "dbt_project" / "dbt_packages"
        if packages.is_dir() and not (tree / "dbt_project" / "dbt_packages").exists():
            (tree / "dbt_project" / "dbt_packages").symlink_to(packages)
        stage = "database"
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{dbname}"')
        stage = "mark"
        run(stage, "env", "mark", "--confirm", env_id)
        stage = "bootstrap"
        say(f"bootstrapping {commit[:10]} into {dbname} (this is a full bootstrap)...")
        started = time.monotonic()
        output = run(stage, "pipeline", "bootstrap")
        baseline["bootstrap_seconds"] = round(time.monotonic() - started, 1)
        baseline["timings"] = _timings(output)
        stage = "build"
        run(stage, "dashboard", "rebuild-results")
        run(stage, "dashboard", "build-data")
        stage = "S1"
        # Its bootstrap runs collections side by side (REQ-PIPE-279's rank NFR).
        s1 = snapshot(scratch, run_seq_within_collection=True)
        baseline["surfaces"] = {"S1": {k: {"columns": list(cols),
                                           "rows": sorted([list(r), n] for r, n in rows.items())}
                                       for k, (cols, rows) in s1.items()
                                       if k.startswith("qa.")}}
        stage = "S4"
        baseline["surfaces"]["S4"] = generated_files(tree)
        stage = "S5"
        baseline["surfaces"]["S5"] = reports(tree, report_context(scratch))
        stage = "S7"
        baseline["surfaces"]["S7"] = help_and_menus(tree, env)
        stage = "write"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".partial")
        tmp.write_text(json.dumps(baseline, sort_keys=True))
        tmp.replace(path)  # a failed capture leaves no readable baseline
        return path
    except StageFailed:
        raise
    except Refused:
        raise
    except Exception as exc:  # noqa: BLE001 - every failure names its stage
        raise StageFailed(stage, f"{type(exc).__name__}: {exc}") from exc
    finally:
        try:
            with psycopg.connect(admin, autocommit=True) as conn:
                conn.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        except Exception:  # noqa: BLE001 - the stage's own error is the one to show
            pass
        subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=ROOT,
                       capture_output=True)
        shutil.rmtree(work, ignore_errors=True)
        lock.close()


# ---- compare -----------------------------------------------------------

def load(path_or_label: str) -> dict:
    p = Path(path_or_label)
    if not p.suffix:
        p = baseline_path(path_or_label)
    if not p.is_file():
        raise Refused(f"no baseline at {p}")
    return json.loads(p.read_text())


def _diff_mapping(a: dict, b: dict, limit: int) -> list[str]:
    out = []
    for key in sorted(set(a) | set(b)):
        if key not in a:
            out.append(f"  only in B: {key}")
        elif key not in b:
            out.append(f"  only in A: {key}")
        elif a[key] != b[key]:
            out.append(f"  differs: {key}")
            if isinstance(a[key], (dict, list)):
                out += [f"     {p}" for p in _json_differences(a[key], b[key], 10)]
        if len(out) >= limit:
            out.append("  ...")
            break
    return out


def _json_differences(a, b, limit: int, path: str = "") -> list[str]:
    """The first `limit` JSON paths where two parsed reports differ."""
    out: list[str] = []

    def walk(x, y, p):
        if len(out) >= limit:
            return
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                if k not in x or k not in y:
                    out.append(f"{p}.{k}: only in {'A' if k in x else 'B'}")
                else:
                    walk(x[k], y[k], f"{p}.{k}")
        elif isinstance(x, list) and isinstance(y, list):
            if len(x) != len(y):
                out.append(f"{p}: {len(x)} items vs {len(y)}")
            for i, (u, v) in enumerate(zip(x, y)):
                walk(u, v, f"{p}[{i}]")
        elif x != y:
            out.append(f"{p}: {json.dumps(x, default=str)[:80]} vs "
                       f"{json.dumps(y, default=str)[:80]}")
    walk(a, b, path)
    return out[:limit]


def _diff_s1(a: dict, b: dict, limit: int) -> list[str]:
    out = []
    for table in sorted(set(a) | set(b)):
        if table not in a or table not in b:
            out.append(f"  {table}: present only in {'A' if table in a else 'B'}")
            continue
        if a[table]["columns"] != b[table]["columns"]:
            out.append(f"  {table}: columns differ {a[table]['columns']} vs "
                       f"{b[table]['columns']}")
            continue
        ra = Counter({tuple(r): n for r, n in a[table]["rows"]})
        rb = Counter({tuple(r): n for r, n in b[table]["rows"]})
        only_a, only_b = ra - rb, rb - ra
        if only_a or only_b:
            out.append(f"  {table}: {sum(ra.values())} vs {sum(rb.values())} rows; "
                       f"{sum(only_a.values())} only in A, {sum(only_b.values())} only in B")
            cols = a[table]["columns"]
            for side, extra in (("A", only_a), ("B", only_b)):
                for row in list(extra)[:limit]:
                    out.append(f"     only in {side}: " + ", ".join(
                        f"{c}={v}" for c, v in zip(cols, row))[:300])
    return out


#: REPORT FILES A REQUIREMENT RENAMED, old name -> new, mapped on A's side
#: before S5 is compared. REQ-PIPE-248 criterion 8 makes this available to
#: that requirement ONLY: a rename that any comparison could map would let
#: any change hide a file disappearing behind a new one.
RENAMED_REPORTS = {
    "REQ-PIPE-248": {
        "results_bdm.json": "results_rs_civil-registration.json",
        "results_cp.json": "results_cpfs_child-protection.json",
        "birth_registrations_dashboard.json": "rs_civil-registration_dashboard.json",
        "child_protection_dashboard.json": "cpfs_child-protection_dashboard.json",
    },
}


def compare(a: dict, b: dict, surfaces: list[str], *, limit: int = 5,
            renamed_by: str | None = None) -> dict[str, list[str]]:
    """Differences surface by surface; an empty list where equal (criterion 3).
    `renamed_by` names the requirement whose report renames to map."""
    if renamed_by is not None:
        if renamed_by not in RENAMED_REPORTS:
            raise Refused(f"no report renames are recorded for {renamed_by!r} - only for "
                          f"{', '.join(RENAMED_REPORTS)}")
        renames = RENAMED_REPORTS[renamed_by]
        a = {**a, "surfaces": {**a["surfaces"], "S5": {
            renames.get(k, k): v for k, v in (a["surfaces"].get("S5") or {}).items()}}}
    if a.get("pinned_now") != b.get("pinned_now"):
        raise Refused(f"the two baselines were built with the clock pinned to different "
                      f"instants ({a.get('label')}: {a.get('pinned_now')}, {b.get('label')}: "
                      f"{b.get('pinned_now')}) - recapture one so they compare like with like")
    for key in ("harness", "normaliser"):
        if a.get(key) != b.get(key):
            raise Refused(f"the two baselines were taken by different {key} versions "
                          f"({a.get('label')}: {a.get(key)}, {b.get('label')}: "
                          f"{b.get(key)}) - recapture one so they compare like with like")
    out = {}
    for code in surfaces:
        sa, sb = a["surfaces"].get(code, {}), b["surfaces"].get(code, {})
        out[code] = _diff_s1(sa, sb, limit) if code == "S1" else _diff_mapping(sa, sb, 50)
    return out


def commits_between(a: str, b: str) -> int | None:
    done = subprocess.run(["git", "rev-list", "--count", f"{a}..{b}"], cwd=ROOT,
                          capture_output=True, text=True)
    return int(done.stdout.strip()) if done.returncode == 0 else None
