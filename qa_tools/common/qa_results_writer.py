"""
Records each real QA tool's NATIVE raw output (dbt's run_results.json, a
Soda scan_results dict, a datacontract-cli Run, an Evidently Report
snapshot) in the `qa` metadata schema, alongside the resolved records
the dashboard renders. This is the real source of truth for QA history,
independent of whatever the dashboard currently renders from
`reports/*.json` (which stays exactly as it is today - gitignored,
regenerated, a reshaped VIEW of this data, not the source of it).

IT USED TO WRITE A COMMITTED TREE, under
`qa_results/<agency>/<collection>/<dataset>/<run_id>/<tool>.json`, and
REQ-PIPE-089 replaced that with rows. The reason is Keith's own standing
rule: the repository holds CONFIGURATION, not STATE. QA results are
state - they accumulate, nobody reviews them, and a second person
running the pipeline legitimately produces different bytes.

WHAT THE MOVE COST, recorded so it is a known trade rather than a
discovery: a reader with no database access can no longer read the
history, and the dashboard build had to move out of GitHub Actions,
which cannot reach the database. Both were accepted deliberately.

Deliberately native format, not reshaped into a common schema -
`raw_output` is each tool's own real output, genuinely unmodified, so a
real audit years from now sees exactly what the tool itself produced,
not this project's own interpretation of it.

A second top-level field, `verified`, sits alongside it (never inside
it - `raw_output` stays pristine either way): the same fully-resolved,
dashboard-ready check-result records `evaluate_*()` already builds in
memory every run, captured here too. Added 2026-09-16
(plans/publishing-and-history.md Phase 2, Keith's explicit call) once a
real gap was found: `raw_output` alone isn't trustworthy or sufficient
for two dbt-side bugs plus one Soda-side gap, all already investigated
in full in `plans/qa-pipeline.md` and `qa_tools/bdm/run_dbt_bdm.py`'s
own docstring - not re-derived here, just cited:

1. **dbt-core's `failures=0` accounting bug**, root-caused
   (`plans/qa-pipeline.md` item 34): `dbt/task/test.py`'s
   `build_test_run_result()` (confirmed in our installed dbt-core
   1.12.4's own source) never reassigns `failures` off its `0` default
   when a test's final status lands on "Pass" - so any test whose real
   failure count is nonzero but under every configured threshold (a
   genuine pass) silently reports `failures=0` in `run_results.json`.
   Filed and triaged upstream as a real bug, fix unmerged as of our
   installed version: [dbt-labs/dbt-core#11312](
   https://github.com/dbt-labs/dbt-core/issues/11312).
2. **A second, separate, still-NOT-root-caused nondeterminism**
   (`plans/qa-pipeline.md` items 34 and 38): a test's reported status/
   failures flipping between correct and wrong across separate
   `dbt build` invocations of the identical warehouse file, no code
   change in between. Item 38's own deep, controlled repro (40+
   invocations, isolated and under real parallel load) found and fixed
   a related-but-distinct, fully-explained bug along the way (a missing
   `fail_calc:` override in this project's own `schema.yml`, nothing to
   do with dbt-core itself) but never reproduced the original flip - it
   remains open, unexplained, and has no upstream issue filed (points at
   dbt-duckdb's query execution path, not dbt-core's result-reporting
   logic, so there's nothing to link beyond this repo's own account).
3. **Soda's `row_count_total` isn't in `scan_results` at all** - not a
   Soda bug, just a genuine gap in what that structure exposes (no
   issue to cite, upstream or otherwise).

Both dbt problems are exactly what `run_dbt_bdm.py`'s/`run_dbt_cp.py`'s
`_AUDIT_AGGREGATE_SQL` audit-table re-query protects against "at once"
(their own docstrings' wording) - it doesn't care which of the two
produced a wrong number, it re-derives the truth from dbt's own
`--store-failures` audit table regardless. That query, and Soda's
`row_count_total` query, both need a live connection to that run's own
per-run DuckDB warehouse - which only exists while the tool is actually
running, not when this history is read back later. Rather than have
Phase 2's dashboard-pipeline read step depend on that ephemeral
warehouse too (or silently trust numbers known to sometimes be wrong),
each `run_*.py` caller now writes `verified` once, at the point that
live connection already exists - so reading committed history back
later needs nothing beyond this file. Every tool writes `verified` the
same way, even the 2 (datacontract-cli, Evidently) whose `raw_output`
never needed correcting - uniform shape, so the reader
(`qa_results_reader.py`) never has to special-case which tools happen
to need it.

THE THREE SCOPES SURVIVED THE MOVE (REQ-PIPE-038, REQ-QAC-037) as a
column rather than as a directory, because they are about what a record
DESCRIBES rather than about where it is kept:

    a dataset's own id
        that dataset's own resolved records, and nothing else.
    `_cross-table`
        the records that span datasets (REQ-QAC-037).
    `_raw`
        the one genuinely-unmodified `raw_output` per invocation, plus
        the `dataset_stats` and `tables_read` pseudo-tools, which
        describe a RUN rather than a dataset.

A leading underscore stays a RESERVED name the hierarchy gate refuses
for any agency, collection or dataset id, which is what keeps every
scope unambiguously distinct from a dataset.

ONE CALL STILL RECORDS SEVERAL THINGS. A Child Protection Soda scan is
one `Scan()` over six tables, and its 50 results fan out to six
datasets while its scan document is recorded once. Before REQ-PIPE-038
both collections recorded one document per tool per run at collection
level, so finding one table's history meant filtering that through a map
somebody maintained by hand.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

def _with_tables_read(verified: list[dict], run_id: str) -> list[dict]:
    """Record, on each cross-table check's own result, the physical
    table name of every OTHER table it read (REQ-PIPE-036 criterion 10).

    HERE RATHER THAN IN EACH TOOL, because this is the one place all
    eight run_*.py callers already funnel through - and doing it in
    four tool modules twice over is four chances for one of them to be
    missed, which produces a result that looks complete and names none
    of what it read.

    THE RESOLUTION IS READ ONLY WHERE SOMETHING DECLARES A DEPENDENCY.
    Birth Registrations has no cross-table check at all, so its four
    writes never open a connection; Child Protection's do. A run with
    no recorded resolution - a fixture, an ad hoc call - gets no
    tables_read rather than an error, and that is safe to be quiet
    about for one specific reason: the run-level tables_read.json
    (REQ-PIPE-068 criterion 5) records the same resolution for the
    whole run, so an absence here is visible against a file that is
    always written.
    """
    from qa_tools.common import tables_read as tables_read_mod

    declared = _declared_reads_tables()
    if not any(record.get("check_id") in declared for record in verified):
        return verified
    try:
        from qa_tools.common import supply_db

        conn = supply_db.connect(read_only=True)
        try:
            resolution = supply_db.resolution_for(conn, run_id)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - see the docstring on why this is quiet
        return verified
    from qa_tools.common import period_tables

    # A PERIOD TABLE IS RECORDED BY THE SUPPLY IT HELD (REQ-PIPE-129
    # criterion 13), as the stamped name that supply's table carries
    # everywhere but a period - its plain name there says nothing.
    resolved = {logical: (period_tables.stamped_name(logical, resolution.supply_of[logical])
                          if logical in resolution.supply_of else physical)
                for logical, physical in resolution.resolved.items()}
    return tables_read_mod.attach(verified, resolved, declared)


@lru_cache(maxsize=1)
def _declared_reads_tables() -> dict[str, list[str]]:
    """`check_id` -> the tables that check declares it reads.

    Cached because it parses every check source and the answer cannot
    change within one process - a check definition is a file on disk,
    and a run that edited one mid-flight would have bigger problems.
    """
    from qa_tools.common import tables_read as tables_read_mod
    from qa_tools.common.validate_check_lifecycle import collect_checks

    try:
        return tables_read_mod.declared_by_check_id(collect_checks(None))
    except Exception:  # noqa: BLE001 - a malformed source is the lifecycle gate's to report
        return {}


def run_owner(run_id: str) -> tuple[str, str] | None:
    """(dataset id, logical table) a run checks, read off its id - or
    None for an id that names no table (a fixture's, a trial's).

    A RUN ID IS ITS STAGED TABLE'S SPELLING since REQ-PIPE-105 (Keith,
    2026-10-02), so it says which table the run is for. Reading it from
    the id rather than taking an argument is what lets all eight tool
    callers stay as they are.
    """
    from qa_tools.common import hierarchy, supply_db

    parts = supply_db.split_staged(run_id)
    if parts is None:
        return None
    try:
        return hierarchy.dataset_for_table(parts[0]).dataset_id, parts[0]
    except Exception:  # noqa: BLE001 - not one of ours means not scoped
        return None


def _scope_to_run(verified: list[dict], run_id: str) -> None:
    """Keep only what this run is FOR, in place (REQ-PIPE-105 criterion
    11; Keith's call 2026-10-02, "own + readers").

    One file is one arrival, and its run reads the whole period through
    the overlay - so the tools evaluate every sibling's checks too. Those
    are about supplies other runs already checked, and recording them
    here would QA each supply once per sibling: six copies per Child
    Protection delivery, under six run ids. What a run records is:

      - checks filed against its OWN dataset, and
      - cross-table checks that declare they READ its table - the
        re-evaluation REQ-QAC-037 criterion 4 asks for when a table they
        depend on arrives.

    A CONTESTED OWN TABLE KEEPS ONLY THE SECOND (REQ-PIPE-079 criterion
    13): its view fell through to the period's promoted version, so its
    own checks would report on data this supplier did not send.

    IN PLACE, because every caller returns the very list it passed here
    and the orchestrator writes reports/results_*.json from that - a
    filtered copy recorded here and an unfiltered one returned would be
    the two-build-paths divergence this module already fixed once.
    """
    owner = run_owner(run_id)
    if owner is None or not verified:
        return
    dataset_id, table = owner
    contested = False
    if any(r.get("dataset_id") == dataset_id for r in verified):
        try:
            from qa_tools.common import supply_db

            conn = supply_db.connect(read_only=True, label="mothman:run-scope")
            try:
                contested = table in supply_db.resolution_for(conn, run_id).ambiguous
            finally:
                conn.close()
        except Exception:  # noqa: BLE001 - no resolution means nothing contested
            contested = False
    # WHICH CHECKS THIS ARRIVAL SETS OFF is reevaluation.plan()'s answer
    # (REQ-PIPE-079 criterion 6), not a second copy of it here - plan()'s
    # own docstring names a fourth implementation of "which checks touch
    # this table" as how they come to disagree. Within THIS run's period
    # only, which the overlay already guarantees; the period is carried on
    # the plan for the record.
    from qa_tools.common import reevaluation

    readers = reevaluation.plan(table=table, period=_period_of_run(dataset_id, run_id),
                                reads=_declared_reads_tables()).check_ids
    verified[:] = [
        r for r in verified
        if (r.get("dataset_id") == dataset_id and not contested)
        or r.get("check_id") in readers]
    # A RE-EVALUATION NAMES ITS CAUSE (criterion 7). A check belonging to
    # ANOTHER dataset is here only because it reads this run's table, so
    # this arrival is why it was evaluated again - "this went red when
    # carers arrived" rather than a verdict that changed with nobody
    # touching its dataset. reevaluation.mark() names it; each record is
    # replaced IN THE CALLER'S OWN LIST, for the reason the filter above is.
    for i, record in enumerate(verified):
        if record.get("dataset_id") != dataset_id:
            verified[i] = reevaluation.mark(record, caused_by=run_id)


def scope_of_run(run_id: str):
    """`_scope_to_run()`'s rule as a predicate on a check id - what the
    left-out reconciliation (REQ-PIPE-115 criterion 17) compares within,
    so the two cannot disagree about which checks are this run's.
    Everything is in scope for a run id that names no table."""
    from qa_tools.common import check_id as check_id_mod
    from qa_tools.common import reevaluation, supply_db

    owner = run_owner(run_id)
    if owner is None:
        return lambda check: True
    dataset_id, table = owner
    try:
        conn = supply_db.connect(read_only=True, label="mothman:run-scope")
        try:
            contested = table in supply_db.resolution_for(conn, run_id).ambiguous
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - no resolution means nothing contested
        contested = False
    readers = reevaluation.plan(table=table, period=_period_of_run(dataset_id, run_id),
                                reads=_declared_reads_tables()).check_ids

    def in_scope(check: str) -> bool:
        parsed = check_id_mod.try_parse(check)
        own = parsed is not None and parsed.dataset == dataset_id
        return (own and not contested) or check in readers
    return in_scope


def _period_of_run(dataset_id: str, run_id: str) -> str:
    """The period this run's supply was filed to, or "" where that cannot
    be read - it is carried on the plan for the record, and never decides
    what is kept (the run's overlay is already one period)."""
    from qa_tools.common import filing, supply_db

    parts = supply_db.split_staged(run_id)
    if parts is None:
        return ""
    try:
        return filing.period_for_key(dataset_id, parts[1]) or ""
    except Exception:  # noqa: BLE001 - informational only, see above
        return ""


def write_qa_result(agency: str, collection: str, run_id: str, run_timestamp: str,
                     tool: str, raw_output: Any, verified: list[dict] | None = None,
                     run_by: str | None = None) -> None:
    """Records one tool's native raw output for one run. `raw_output` must
    already be JSON-serializable (a plain dict/list) - each run_*.py
    caller is responsible for converting its own tool's native result
    object first (e.g. a Pydantic model's `.model_dump()`, an Evidently
    snapshot's `.dict()`) since that conversion is tool-specific, not
    something this generic writer should need to know about.

    `verified` is the caller's already-built list of fully-resolved
    check-result dicts for this tool+run (see this module's own
    docstring for why it exists alongside `raw_output`, not instead of
    it) - optional only so tests and one-off calls that don't care about it
    can omit it; every real `run_*.py` caller passes it.

    `run_by` (qa_tools/common/git_identity.py's get_run_by(), the local
    git user.email) is the changelog feature's attribution field
    (plans/publishing-and-history.md Phase 3, 2026-09-16) - only
    orchestrate_bdm.py's/orchestrate_cp.py's own `dataset_stats` write
    passes it, since one value per run is all the changelog needs
    (qa_tools/common/changelog.py reads it from there); the other 8
    run_*.py callers leave it None, same "always present as a key,
    defaulted" shape `verified` already uses.

    Records `run_timestamp` (and `run_by`) alongside the raw output
    rather than inside it - this never mutates what the tool actually
    produced, so provenance is carried without touching the payload.

    ONE CALL RECORDS SEVERAL THINGS (REQ-PIPE-038). The second argument
    is the COLLECTION - it was named `dataset` when Child Protection's
    four tools all recorded one collection-level document, and the
    rename is the point of the change rather than tidying: each
    `verified` record goes to the dataset it names, the raw output is
    recorded once against `_raw`, and a spanning record goes to
    `_cross-table` (REQ-QAC-037)."""
    if verified:
        _scope_to_run(verified, run_id)
    records = _with_tables_read(verified or [], run_id)
    # THE CALLER'S OWN RECORDS ARE BROUGHT UP TO DATE, and that is not
    # tidiness. The orchestrator keeps the list it passed here and
    # writes it to reports/results_*.json, which is what a LOCAL
    # dashboard build reads - while CI rebuilds from the committed
    # files instead. Enriching only the copy written to disk left the
    # two build paths producing different dashboards from the same run:
    # measured at 432 results carrying tables_read from committed
    # history and none from the live run. Nothing rendered it yet, so
    # nothing failed; the next thing to read it would have seen one
    # answer locally and another in CI.
    for original, enriched in zip(verified or [], records):
        original.update(enriched)
    # CRITERION 1: a check spanning more than one dataset is recorded
    # against a scope of its own, never against one of the datasets it
    # touches - which one it got filed under was arbitrary, and the
    # arbitrariness is the whole defect. CRITERION 2: it moves, it is
    # not copied; a record kept in two places is two records to keep in
    # step.
    declared = _declared_reads_tables()

    # WHETHER EACH RECORD IS REAL QUALITY HISTORY, DECIDED HERE ALONGSIDE
    # WHOSE IT IS (REQ-PIPE-106 criteria 10 and 15). A result about a
    # dataset that has declared it has no calendar is recorded as
    # IN-DEVELOPMENT, and a cross-table check is in-development where ANY
    # participant is - so a mixed check cannot move an agreed dataset's
    # verdict, because the agreed dataset's own page reads AGREED results
    # and this is not one.
    #
    # DERIVED, NEVER PASSED IN, which is the whole reason it is here rather
    # than an argument on this function. Ten callers pass `verified` and any
    # one of them could forget a `sample=True`; none of them can forget to
    # be this line.
    from qa_tools.common import qa_store as _qa_store
    from qa_tools.common import sample_data

    own_by_state: dict[str, list[dict]] = _empty_states()
    spanning_by_state: dict[str, list[dict]] = _empty_states()
    sample_ids = sample_data.sample_dataset_ids()
    for index, record in enumerate(records):
        if record.get("check_id") in declared:
            state = sample_data.state_for_participants(
                _participants(record.get("check_id"), declared), sample_ids=sample_ids)
            spanning_by_state[state].append(record)
        else:
            state = sample_data.supply_state(record.get("dataset_id"),
                                             sample_ids=sample_ids)
            own_by_state[state].append(record)
        # AND SAID ON THE RECORD ITSELF, for the in-development ones only.
        # The reader drops it again for an agreed record
        # (qa_results_reader's `_NOT_IN_A_RECORD`), and the reason both ends
        # agree is that a LIVE run writes reports/results_*.json from the
        # list it holds in memory while a rebuild reads it out of the
        # database - so a field on one and not the other would make the two
        # paths produce different dashboards from the same run. That has
        # happened here before, measured at 432 results carrying tables_read
        # from committed history and none from the live run.
        #
        # ONLY THE IN-DEVELOPMENT ONES, so an agreed record keeps the exact
        # twenty keys it has always had. `supply_state` is a key column, so
        # record_results drops it rather than duplicating it into `extra`.
        if state == _qa_store.IN_DEVELOPMENT:
            record["supply_state"] = _qa_store.IN_DEVELOPMENT
            if verified and index < len(verified):
                verified[index]["supply_state"] = _qa_store.IN_DEVELOPMENT

    # THE FAN-OUT, INTO THE DATABASE (REQ-PIPE-089). It writes a
    # committed tree of JSON files as well until this line's own history
    # caught up with it: the rules just above - a spanning record belongs
    # to no dataset, raw output describes the invocation and is recorded
    # once, the two pseudo-tools describe a run - ARE the fan-out, and
    # two implementations of them were two things to keep in step. So
    # the file half was deleted from underneath this call rather than
    # beside it, leaving the rules in one place.
    #
    # REQ-PIPE-038 CRITERION 1 still holds here, and is what `own`
    # carries: every result against the dataset it DESCRIBES, which is
    # the dataset its own record names - not the one the tool happened to
    # be invoked against. CRITERION 3: Birth Registrations goes through
    # the identical code path even though its collection holds exactly
    # one dataset and the keying buys that collection nothing. A
    # one-dataset collection is precisely where a special case would look
    # harmless.
    _record_in_database(agency, collection, run_id, run_timestamp, tool,
                        raw_output, own_by_state, spanning_by_state, run_by)


def _participants(check_id: str | None, declared: dict[str, list[str]]) -> list[str]:
    """The dataset ids a cross-table check reads, from its declaration.

    A table the hierarchy does not map is SKIPPED rather than raised on:
    the declaration is authored prose and the hierarchy gate is what
    reports a name that resolves to nothing. Skipping is safe here for one
    specific reason - a table nobody can resolve is not a configured
    calendar-less dataset, so it cannot be the participant that makes this
    check in-development.
    """
    from qa_tools.common import hierarchy

    out = []
    for table in declared.get(check_id) or ():
        try:
            out.append(hierarchy.dataset_for_table(table).dataset_id)
        except Exception:  # noqa: BLE001 - see the docstring
            continue
    return out


def _empty_states() -> dict[str, list[dict]]:
    """One bucket per `supply_state`, both present even when empty.

    THE EMPTY ONE IS LOAD-BEARING, and it is the same reasoning the write
    below already has for writing an empty scope: each `record_results`
    call REPLACES that (run, tool, scope, supply_state), so "this tool
    found nothing in-development this time" has to clear what it found last
    time. A dataset that GRADUATES between two runs is exactly that case -
    its next run records nothing in-development, and the stale
    in-development verdicts have to go rather than stand beside the real
    ones for ever.
    """
    from qa_tools.common import qa_store

    return {qa_store.AGREED: [], qa_store.IN_DEVELOPMENT: []}


#: The two pseudo-tools. Neither is a QA tool - they describe a RUN -
#: and each lands in a table of its own rather than in `tool_output`.
DATASET_STATS_TOOL = "dataset_stats"
TABLES_READ_TOOL = "tables_read"

#: `qa.dataset_stats` is keyed (run, dataset) because decision 2 said so,
#: and what is actually written today is ONE COLLECTION-LEVEL document
#: per run - Child Protection's holds `row_counts` for six tables inside
#: it. The empty string is that document, the same convention
#: `qa.tool_output` already uses for output that belongs to no one
#: dataset. Keeping the key rather than collapsing it means splitting the
#: payload per dataset later needs no migration.
RUN_LEVEL = ""


def _record_in_database(agency: str, collection: str, run_id: str, run_timestamp: str,
                         tool: str, raw_output: Any, own_by_state: dict[str, list[dict]],
                         spanning_by_state: dict[str, list[dict]],
                         run_by: str | None) -> None:
    """Record one tool's output for one run in the metadata schema.

    THE RUN KEY IS THE RUN ID, which is safe because this project
    already requires run ids to be globally unique: `supply_db
    .run_schema(run_id)` puts every run's views in one schema namespace
    regardless of collection, so a collision would already be a
    collision there. Inheriting that constraint beats inventing a
    compound key that reads worse everywhere.

    REGISTERING THE RUN IS DEFENSIVE HERE. The orchestrator registers it
    properly, knowing who is running it; this call knows only what its
    arguments say, which for eight of the ten writers is no identity at
    all. `record_run` coalesces rather than overwriting for exactly that
    reason, and `complete_run` is where a missing identity is refused.
    """
    from qa_tools.common import environments, qa_store, supply_db

    environment = environments.current_or_none()
    with supply_db.connect(label="mothman:qa-results") as conn:
        qa_store.ensure_schema(conn)
        qa_store.record_run(conn, run_key=run_id, agency_id=agency,
                            collection_id=collection, run_timestamp=run_timestamp,
                            run_by=run_by,
                            environment=environment.id if environment else None)

        if tool == DATASET_STATS_TOOL:
            qa_store.record_dataset_stats(conn, run_id, RUN_LEVEL, raw_output)
        elif tool == TABLES_READ_TOOL:
            qa_store.record_tables_read(conn, run_id, (raw_output or {}).get("resolved", {}),
                                        (raw_output or {}).get("supply_of", {}))
        else:
            qa_store.record_tool_output(conn, run_id, tool, raw_output)

        # BOTH SCOPES ARE WRITTEN EVEN WHEN EMPTY, because each call
        # REPLACES that (run, tool, scope) - so "this tool found nothing
        # this time" has to clear what it found last time. Skipping the
        # empty case would leave a stale verdict standing, which is the
        # file-based equivalent of not rewriting a file.
        #
        # AND EVERY STATE, for the same reason (REQ-PIPE-106). A dataset
        # that graduates between two runs records nothing in-development on
        # the second, and the first run's in-development verdicts have to be
        # cleared rather than left standing beside the real ones.
        keys = {"tool": tool, "agency_id": agency, "collection_id": collection}
        for state, group in own_by_state.items():
            qa_store.record_results(conn, run_id, group, **keys, supply_state=state)
        for state, group in spanning_by_state.items():
            qa_store.record_results(conn, run_id, group, **keys,
                                    scope=qa_store.CROSS_TABLE_SCOPE,
                                    supply_state=state)


def open_run(agency: str, collection: str, run_id: str, run_timestamp: str,
             run_by: str) -> None:
    """Register a run before any of its tools write, with the identity
    only the orchestrator knows (REQ-PIPE-089 criteria 6 and 13).

    A tool's own write registers the run too, defensively, because
    `mothman debug run-dbt` invokes one tool with no orchestrator around
    it. The difference is that this call knows WHO is running it, and
    `record_run` coalesces so the defensive registrations cannot undo
    that.
    """
    from qa_tools.common import environments, qa_store, supply_db

    with supply_db.connect(label="mothman:qa-run-open") as conn:
        qa_store.ensure_schema(conn)
        qa_store.record_run(conn, run_key=run_id, agency_id=agency,
                            collection_id=collection, run_timestamp=run_timestamp,
                            run_by=run_by, environment=environments.current().id)
        # A RE-RUN STARTS INCOMPLETE AGAIN. Without this, re-running a
        # run that finished once would leave its results observable
        # while the new ones were still being written - a reader would
        # see the old run's verdicts mixed with however much of the new
        # one had landed, which is the partial-run problem wearing the
        # one disguise the completeness marker does not catch.
        qa_store.reopen_run(conn, run_id)


def finish_run(run_id: str) -> None:
    """Mark a run complete, which is what makes its results observable.

    Called only where every tool has written. A run that raised never
    reaches this, so its partial results stay invisible and an operator
    finds it through `qa_store.incomplete_runs()` - which is criteria 13
    and 20 being the same mechanism rather than two.
    """
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(label="mothman:qa-run-finish") as conn:
        qa_store.complete_run(conn, run_id)
        # THE CENSUS ON EVERY QA RUN (REQ-PIPE-081 criterion 12), where a
        # connection is legitimately open - never by the dashboard build.
        from qa_tools.common import census

        try:
            census.take(conn, trigger="qa-run", run_key=run_id)
        except Exception as exc:  # noqa: BLE001 - the run's results stand regardless
            print(f"note: the census after {run_id} could not be taken "
                  f"({type(exc).__name__}: {exc}).")
