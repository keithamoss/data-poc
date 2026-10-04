"""Reading QA history back (REQ-PIPE-089).

IT USED TO WALK A COMMITTED FILE TREE. Every function here answered
its question by globbing `qa_results/<agency>/<collection>/...` and
opening JSON; the tree is gone and the same questions are now queries
against the `qa` metadata schema. THE SIGNATURES ARE UNCHANGED, which
is deliberate: ten callers read through this module, including both
`build_results_from_history.py` modules whose whole job is to produce
a file byte-identical to a live run's, and a reader swap that also
changed the interface would have made "did the move preserve
behaviour" impossible to answer by diffing.

WHAT GOT BETTER RATHER THAN MERELY MOVED:

  COMPLETENESS IS RECORDED, NOT INFERRED. `run_is_complete` used to
  mean "all six expected files are present", which is a proxy - a run
  that died after writing its last file looked complete. `qa.run` has
  a `completed_at` that the orchestrator sets once every tool has
  written, so the question has a real answer. The file-count check
  survives as `missing_tools`, because "which tool did not write" is
  still the useful diagnostic once a run IS known incomplete.

  `qa_results_dir` IS GONE FROM EVERY SIGNATURE. It was accepted and
  ignored for one commit, so that ten call sites did not all have to
  change alongside the storage; REQ-PIPE-089's last phase removed both
  the parameter and the tree it named.

WHAT IT MAY READ, and the line is Keith's own (2026-09-27): a build
may read recorded QA results, never actual data, and never anything
else. Everything here goes through `qa_store`, which knows only about
the metadata schema - no staging, rejected, promoted or period schema
is reachable from this module at all.
"""
from __future__ import annotations

import re

from qa_tools.common import qa_store, supply_db

_DIGIT_RUN = re.compile(r"(\d+)")


def _natural_sort_key(name: str) -> tuple:
    """Sorts run_id-shaped strings ("run_5_2026-01-01", "cp_run_005_...",
    "run_120_2026-09-18_resupply2") in real numeric/chronological order
    regardless of how many digits any of their numbers happen to have -
    a plain string sort of these (what both this module's own callers
    used to do) silently breaks the moment a run number crosses a fixed
    zero-padding width (2026-09-17: generator/generate_runs.py's
    delivery/run numbering went 60->120 deliveries and immediately hit
    exactly this - "delivery_100" < "delivery_11" as plain strings - a
    real bug a test caught; see that module's own comment). Keith's own
    call once that surfaced: this dataset's real run count will keep
    growing into the thousands over the life of the project, so a wider
    FIXED width (":03d" instead of ":02d") is not a real fix, just a
    bigger version of the same bug waiting to reoccur - this splits the
    string into alternating text/number runs and compares numbers as
    ints instead, so it's correct at any width, forever, with no digit
    count to eventually outgrow."""
    return tuple(int(part) if part.isdigit() else part for part in _DIGIT_RUN.split(name))

# Matches orchestrate_bdm.py's/orchestrate_cp.py's own _run_one()
# construction order - keeps a history-rebuilt results list in the same
# run-then-tool order a live orchestrator run always produced, so a diff
# against a live run's own reports/*.json output is a real equivalence
# check, not noise from an incidental reordering.
TOOL_ORDER = ["dbt", "soda", "datacontract", "evidently"]

#: Every file a COMPLETE run writes AT COLLECTION LEVEL - the four real
#: tools' raw output plus the two pseudo-tools (REQ-PIPE-036 criterion
#: 12). A run missing any of these failed partway through, and the
#: point of deriving completeness this way rather than writing a marker
#: file is that there is no third state to get wrong: a run is complete
#: because everything it owes is there, not because something said so.
#:
#: These live in RAW_SCOPE since REQ-PIPE-038, which is what makes the
#: rule uniform - every invocation writes its raw output there whether
#: or not it produced a record for any given dataset.
EXPECTED_TOOLS = tuple(TOOL_ORDER) + ("dataset_stats", "tables_read")


# Matches orchestrate_bdm.py's/orchestrate_cp.py's own _run_one()
# construction order - keeps a history-rebuilt results list in the same
# run-then-tool order a live orchestrator run always produced, so a diff
# against a live run's own reports/*.json output is a real equivalence
# check, not noise from an incidental reordering.
TOOL_ORDER = ["dbt", "soda", "datacontract", "evidently"]

#: Every tool a COMPLETE run records at collection level - the four
#: real ones plus the two pseudo-tools (REQ-PIPE-036 criterion 12).
EXPECTED_TOOLS = tuple(TOOL_ORDER) + ("dataset_stats", "tables_read")

#: Every tool whose records are CHECK RESULTS, in the order they are
#: read back: the four real tools, then the two pseudo-tools that record
#: a check which could NOT be evaluated - `unrunnable` (REQ-PIPE-105
#: criterion 13) and `held` (REQ-PIPE-078 criterion 10).
#:
#: SEPARATE FROM TOOL_ORDER ON PURPOSE, because the two answer different
#: questions. TOOL_ORDER is what a complete run OWES (completeness) and
#: what a check id's tail names; a pseudo-tool is owed by no run - a run
#: with nothing unreadable writes nothing there - so adding it to
#: TOOL_ORDER would make every clean run incomplete. But a reader that
#: walks only TOOL_ORDER drops every can't-run red on rebuild, and the
#: check vanishes from the dashboard instead of reading red
#: (plans/post-build-review.md #77, gap 1). Literal names rather than an
#: import of those modules, which import this one;
#: tests/test_qa_results_reader.py pins them to each module's own TOOL.
RESULT_TOOLS = tuple(TOOL_ORDER) + ("unrunnable", "held")


def expected_tools_for(dataset: str) -> tuple[str, ...]:
    """The tools a given DATASET owes a file, derived from the checks
    actually defined against it (REQ-PIPE-038, Keith 2026-09-26).

    Not the fixed list above. A fixed rule reports a dataset
    permanently incomplete for a tool that does not check it, and a
    completeness signal that is always false says nothing about the
    thing it exists to catch. Rejected writing an empty record for the
    tools that did not run: a record that exists asserts the tool ran,
    and it did not.

    THE WORKED EXAMPLE THIS DOCSTRING USED TO GIVE has changed sides,
    which is the best evidence being derived was worth it. Evidently
    defined exactly ONE check in the whole Child Protection collection,
    on cp-notifications, so five of six datasets owed it nothing.
    REQ-QAC-108 gave every Child Protection dataset a relative volume
    check on 2026-09-29, so all six owe one now - and nothing had to be
    configured for that to become true.

    Derived rather than configured, so adding a dataset's first
    Evidently check changes what that dataset owes with no list to
    remember.
    """
    from pipeline.dashboard_check_labels import try_parse
    from qa_tools.common.validate_check_lifecycle import collect_checks

    tools = set()
    for check in collect_checks(None):
        parsed = try_parse(check.check_id)
        if parsed and parsed.dataset == dataset:
            tools.add(_TOOL_OF_CHECK(check.check_id))
    return tuple(tool for tool in TOOL_ORDER if tool in tools)


def _TOOL_OF_CHECK(check_id: str) -> str:
    """Which of the four tools wrote a check, from its id's own tail -
    every tail ends `_dbt`, `_soda`, `_datacontract` or `_evidently`
    (REQ-QAC-023's naming rule, which the lifecycle gate enforces)."""
    tail = check_id.rsplit(".", 1)[-1]
    for tool in TOOL_ORDER:
        if tail.endswith(f"_{tool}"):
            return tool
    return ""


def _conn(given=None):
    """A connection to read through, opened if the caller has none."""
    if given is not None:
        return given, False
    conn = supply_db.connect(label="mothman:qa-history")
    qa_store.ensure_schema(conn)
    return conn, True


def _datasets_in(conn, agency: str, collection: str) -> list[str]:
    return [row[0] for row in conn.execute(
        f'SELECT DISTINCT dataset_id FROM "{qa_store.SCHEMA}".check_result_visible '
        "WHERE agency_id = ? AND collection_id = ? AND dataset_id IS NOT NULL "
        "ORDER BY dataset_id", [agency, collection]).fetchall()]


def missing_tools(agency: str, collection: str, run_id: str,
                  conn=None) -> list[str]:
    """What this run still owes, or [] where it owes nothing.

    STILL THE PER-TOOL DIAGNOSTIC it always was, and no longer the
    definition of completeness - `qa.run.completed_at` is that now.
    The distinction matters: this answers "which tool did not write",
    which is what an operator wants once a run is known to have died,
    and it answered "is this run finished" only because nothing better
    existed.

    A dataset's owings are derived rather than fixed, so the five
    Child Protection datasets Evidently has no check for are not
    reported as permanently incomplete.
    """
    conn, mine = _conn(conn)
    try:
        recorded = {row[0] for row in conn.execute(
            f'SELECT DISTINCT tool FROM "{qa_store.SCHEMA}".tool_output '
            "WHERE run_key = ?", [run_id]).fetchall()}
        has_stats = bool(conn.execute(
            f'SELECT 1 FROM "{qa_store.SCHEMA}".dataset_stats WHERE run_key = ?',
            [run_id]).fetchall())
        has_tables = bool(conn.execute(
            f'SELECT 1 FROM "{qa_store.SCHEMA}".tables_read WHERE run_key = ?',
            [run_id]).fetchall())
        missing = [f"_raw/{tool}" for tool in TOOL_ORDER if tool not in recorded]
        if not has_stats:
            missing.append("_raw/dataset_stats")
        if not has_tables:
            missing.append("_raw/tables_read")

        by_dataset: dict[str, set[str]] = {}
        for dataset_id, tool in conn.execute(
                f'SELECT DISTINCT dataset_id, tool FROM "{qa_store.SCHEMA}".check_result '
                "WHERE run_key = ? AND dataset_id IS NOT NULL", [run_id]).fetchall():
            by_dataset.setdefault(dataset_id, set()).add(tool)
        for dataset in sorted(by_dataset):
            missing += [f"{dataset}/{tool}" for tool in expected_tools_for(dataset)
                        if tool not in by_dataset[dataset]]
        return missing
    finally:
        if mine:
            conn.close()


def run_is_complete(agency: str, collection: str, run_id: str,
                    conn=None) -> bool:
    """Whether the run SAID it finished (REQ-PIPE-089 criterion 13).

    It used to mean "all six expected files are present", which is a
    proxy for the question rather than the question: a run that died
    after writing its last file looked complete, and a run whose last
    tool legitimately produced nothing looked broken. There is one
    place that flips now.
    """
    conn, mine = _conn(conn)
    try:
        return bool(conn.execute(
            f'SELECT 1 FROM "{qa_store.SCHEMA}".run_visible WHERE run_key = ?',
            [run_id]).fetchall())
    finally:
        if mine:
            conn.close()


def incomplete_runs(agency: str, collection: str,
                    conn=None) -> dict[str, list[str]]:
    """Every run under this collection that failed partway, and what
    each is missing."""
    conn, mine = _conn(conn)
    try:
        started = {row[0] for row in conn.execute(
            f'SELECT run_key FROM "{qa_store.SCHEMA}".run '
            "WHERE agency_id = ? AND collection_id = ? AND completed_at IS NULL",
            [agency, collection]).fetchall()}
        return {run_id: missing_tools(agency, collection, run_id, conn=conn)
                for run_id in sorted(started, key=_natural_sort_key)}
    finally:
        if mine:
            conn.close()


def read_one(agency: str, collection: str, run_id: str, tool: str,
             dataset: str | None = None, conn=None, *,
             supply_state: str | None = qa_store.AGREED) -> list[dict]:
    """One tool's `verified` records for one run.

    With `dataset`, that one dataset's. Without it, every dataset under
    the collection in dataset order - which is what a caller asking for
    "this run's dbt results" meant before REQ-PIPE-038 split them, and
    still means.

    `[]` where nothing was recorded, which is ordinary rather than an
    error: a tool with no check defined against a dataset records
    nothing for it.

    `supply_state` DEFAULTS TO AGREED, and `None` means every state
    (REQ-PIPE-106 criterion 10). The default is the safe direction: a
    caller has to ASK to see verdicts from a dataset nobody has agreed a
    schedule for, so a reader that has never heard of this requirement
    cannot accidentally count check development as quality history.
    """
    conn, mine = _conn(conn)
    try:
        sql = (f'SELECT * FROM "{qa_store.SCHEMA}".check_result_visible '
               "WHERE run_key = ? AND agency_id = ? AND collection_id = ? "
               "AND tool = ? AND scope = ?")
        params = [run_id, agency, collection, tool, qa_store.DATASET_SCOPE]
        if supply_state is not None:
            sql += " AND supply_state = ?"
            params.append(supply_state)
        if dataset is not None:
            sql += " AND dataset_id = ?"
            params.append(dataset)
        return _records(conn.execute(sql + " ORDER BY dataset_id, id", params),
                        run_id, _run_timestamp(conn, run_id))
    finally:
        if mine:
            conn.close()


def read_raw(agency: str, collection: str, run_id: str, tool: str,
             conn=None) -> dict | None:
    """The whole envelope one invocation recorded - `raw_output` plus
    its provenance fields - or None where that invocation recorded
    nothing.

    The envelope is REASSEMBLED rather than stored as one: provenance
    lives on the run and the payload on the tool output, which is what
    stops a verdict query dragging megabytes it does not want.
    """
    conn, mine = _conn(conn)
    try:
        run = conn.execute(
            f'SELECT run_timestamp, run_by FROM "{qa_store.SCHEMA}".run_visible '
            "WHERE run_key = ?", [run_id]).fetchall()
        if not run:
            return None
        if tool == "dataset_stats":
            payload = qa_store.dataset_stats_for(conn, run_id, "")
        elif tool == "tables_read":
            resolved = qa_store.tables_read_for_run(conn, run_id)
            payload = {"run_id": run_id, "resolved": resolved} if resolved else None
        else:
            payload = qa_store.tool_output_for(conn, run_id, tool)
        if payload is None:
            return None
        timestamp, run_by = run[0]
        return {"run_timestamp": _iso(timestamp), "run_by": run_by,
                "raw_output": payload, "verified": None}
    finally:
        if mine:
            conn.close()


def list_run_ids(agency: str, collection: str,
                 conn=None) -> list[str]:
    """Every COMPLETE run recorded under this agency/collection, sorted.

    Only complete ones, which is criterion 13 and is a change: the file
    version listed whatever had a directory, so a run that died halfway
    appeared in a rebuild with however much of itself had landed.
    """
    conn, mine = _conn(conn)
    try:
        return sorted(
            (row["run_key"] for row in qa_store.runs_for(conn, agency, collection)),
            key=_natural_sort_key)
    finally:
        if mine:
            conn.close()


def read_dataset_stats(agency: str, collection: str, run_id: str,
                       conn=None) -> dict | None:
    """The precomputed value-counts/arrival/check-aggregate/manifest-entry
    data for one run (qa_tools/<bdm|cp>/dataset_stats.py's output).

    Returns None where the run recorded none, which should not happen
    for any real run - the orchestrator writes it at the one point with
    a legitimate live connection to supply rows, precisely so nothing
    downstream ever needs one.
    """
    conn, mine = _conn(conn)
    try:
        return qa_store.dataset_stats_for(conn, run_id, "")
    finally:
        if mine:
            conn.close()


def read_run_provenance(agency: str, collection: str, run_id: str,
                        conn=None) -> dict | None:
    """The `run_timestamp`/`run_by` pair for one run.

    A separate function from read_dataset_stats() because that one
    returns the PAYLOAD, which is the shape every existing caller
    expects. These two are facts about the run rather than about its
    stats, and are now columns on `qa.run` rather than envelope fields
    beside a payload - which is the same split, made real.
    """
    conn, mine = _conn(conn)
    try:
        rows = conn.execute(
            f'SELECT run_timestamp, run_by FROM "{qa_store.SCHEMA}".run_visible '
            "WHERE run_key = ?", [run_id]).fetchall()
        if not rows:
            return None
        return {"run_timestamp": _iso(rows[0][0]), "run_by": rows[0][1]}
    finally:
        if mine:
            conn.close()


def read_qa_results(agency: str, collection: str,
                    conn=None, *,
                    supply_state: str | None = qa_store.AGREED) -> list[dict]:
    """Every complete run's every tool's `verified` records for one
    agency/collection, in run-id then tool order.

    `supply_state=None` includes the in-development ones - see read_one()."""
    conn, mine = _conn(conn)
    try:
        out: list[dict] = []
        for run_id in list_run_ids(agency, collection, conn=conn):
            for tool in RESULT_TOOLS:
                out.extend(read_one(agency, collection, run_id, tool, conn=conn,
                                    supply_state=supply_state))
        return out
    finally:
        if mine:
            conn.close()


def read_cross_table_results(agency: str, collection: str,
                             conn=None, *,
                             supply_state: str | None = qa_store.AGREED) -> list[dict]:
    """Every recorded cross-table check result for one collection
    (REQ-QAC-037 criterion 1).

    Read from the reserved scope beside the datasets rather than from
    any one of them, which is the whole point: a referential check
    between placements and carers is not cp-placements' result because
    cp-placements is where it happened to be declared.
    """
    conn, mine = _conn(conn)
    try:
        out: list[dict] = []
        for run_id in list_run_ids(agency, collection, conn=conn):
            for tool in RESULT_TOOLS:
                sql = (f'SELECT * FROM "{qa_store.SCHEMA}".check_result_visible '
                       "WHERE run_key = ? AND agency_id = ? AND collection_id = ? "
                       "AND tool = ? AND scope = ?")
                params = [run_id, agency, collection, tool, qa_store.CROSS_TABLE_SCOPE]
                if supply_state is not None:
                    sql += " AND supply_state = ?"
                    params.append(supply_state)
                out.extend(_records(conn.execute(sql + " ORDER BY id", params),
                                    run_id, _run_timestamp(conn, run_id)))
        return out
    finally:
        if mine:
            conn.close()


def _iso(value):
    """A timestamptz back as the ISO string every caller expects."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _run_timestamp(conn, run_id: str):
    """One run's timestamp, which every record it produced carries."""
    rows = conn.execute(
        f'SELECT run_timestamp FROM "{qa_store.SCHEMA}".run WHERE run_key = ?',
        [run_id]).fetchall()
    return rows[0][0] if rows else None


#: THE KEY SET A REAL RECORD HAS, established by counting the committed
#: corpus rather than by reading the evaluators: every `verified` record
#: carries exactly these twenty, whatever their values, plus
#: `tables_read` on the ones that declare it. Reconstructing anything
#: else is a shape change, and a shape change two transforms upstream of
#: the dashboard is the failure CLAUDE.md's own standing lesson is about.
#:
#: Two traps, both hit on the first attempt. A key whose value is NULL
#: is PRESENT in a real record - dropping it breaks
#: `pipeline/build_dashboard_data.py`, which indexes rather than gets.
#: And `tool` is NOT a record key at all: it is a fact about the
#: invocation, stored as a column because the write is keyed on it, and
#: downstream derives it from `check_id`.
#:
#: `supply_state` IS DROPPED FOR AN AGREED RECORD AND KEPT FOR AN
#: IN-DEVELOPMENT ONE (REQ-PIPE-106 criteria 7 and 15). Dropping it
#: outright would leave the dashboard build unable to tell a verdict about
#: a dataset nobody has agreed from a real one, and adding it to all of
#: them is a shape change to a corpus of millions of records for the sake
#: of a value that is `agreed` in every one. So it follows
#: `reference_run_id`'s precedent below: present only where it says
#: something.
_NOT_IN_A_RECORD = ("id", "run_key", "tool", "scope")

#: Present only where the tool actually set it - Evidently's reference
#: run, which the other three have no concept of. A column because it is
#: worth querying; conditional here because adding it as a null to a dbt
#: record would be inventing a key that record never had.
_OPTIONAL = ("reference_run_id",)


def _records(cursor, run_id: str, run_timestamp=None) -> list[dict]:
    """Rows as the `verified` records they were written from.

    `extra` is merged back in rather than returned as a nested field:
    it exists so a fifth tool's own field survives without a migration,
    and a caller should not have to know which of a record's keys
    happened to get a column.
    """
    columns = [d.name for d in cursor.description]
    out = []
    for row in cursor.fetchall():
        record = dict(zip(columns, row))
        stamp = record.pop("run_timestamp", None)
        record.update(record.pop("extra", None) or {})
        for name in _NOT_IN_A_RECORD:
            record.pop(name, None)
        for name in _OPTIONAL:
            if record.get(name) is None:
                record.pop(name, None)
        if record.get("supply_state") == qa_store.AGREED:
            record.pop("supply_state", None)
        record["run_id"] = run_id
        record["run_timestamp"] = _iso(stamp if stamp is not None else run_timestamp)
        out.append(record)
    return out


def canonical_order(results: list[dict]) -> list[dict]:
    """One agreed ordering for a results list, so that a LIVE run and a
    rebuild from committed history produce the same file.

    They stopped agreeing at REQ-PIPE-038 and for a legitimate reason:
    a live Soda scan emits all six Child Protection tables interleaved
    in whatever order its checks ran, while the committed history holds
    them as six per-dataset files a rebuild reads one after another.
    Same records, same counts, different sequence - which would have
    quietly cost this project a real correctness check, since diffing a
    rebuild against a live run is how several behaviour-preserving
    refactors were actually verified.

    A TOTAL order, ending in check_id, and the first version got this
    wrong in a way worth recording. It sorted stably on (run, tool,
    dataset) and left ties to the input order, reasoning that a tool's
    own order for one table is identical down both paths. It is not:
    a live run holds a collection's cross-table records interleaved
    where the tool emitted them, while a rebuild appends them after
    every dataset file it read. Same 3,204 records, 1,494 of them in a
    different position - measured, not predicted.

    (run_id, check_id) is unique in both collections, which is what
    makes a total order available at all: one run produces one result
    per check. Sorting the tail by check_id costs the tool's own
    ordering within one table, which is arbitrary anyway - dbt emits in
    dependency-graph order - and buys an ordering that cannot depend on
    which path assembled the list.
    """
    order = {tool: i for i, tool in enumerate(TOOL_ORDER)}
    return sorted(results, key=lambda r: (
        _natural_sort_key(str(r.get("run_id") or "")),
        order.get(_TOOL_OF_CHECK(str(r.get("check_id") or "")), len(order)),
        str(r.get("dataset_id") or ""),
        str(r.get("check_id") or ""),
    ))
