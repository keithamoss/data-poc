"""Cross-table checks a run CARRIES from a sibling rather than evaluating
again (REQ-PIPE-265, Keith 2026-10-20, option b).

A zip's files share one receipt instant, are filed together before the
first is checked, and each becomes its own run. A cross-table check reads
two of those tables, so each of their runs used to evaluate it - over the
same two supplies, with the same answer every time (2,196 of 2,196 pairs
on the bootstrapped Child Protection history). Now the first run in which
it is in scope evaluates it, and a later sibling CARRIES that verdict:

  - decided BEFORE any tool is invoked, and recorded (qa.carried_check),
    so a gate run later in another process - the processing pass gating a
    checked-but-ungated arrival - finds the same answer;
  - left out of the run's scope (qa_results_writer.scope_of_run), which is
    the ONE rule what each tool is asked for, the writer's filter, the
    left-out reconciliation and the missing-check refusal all share;
  - handed to the later run's promotion gate from the run that evaluated it
    (records_for), so every sibling table's gate reads a verdict for every
    cross-table check that reads it. ONE RECORD, never a copy (REQ-QAC-037
    criterion 2).

ONLY WHAT WAS READ DECIDES (criterion 5). The knock-on and scripted
decisions run between two siblings' runs, so the shared instant does not by
itself mean the same data: every table the check reads must be the same
SUPPLY in both runs - this run's resolution against the qa.check_read the
sibling's result recorded (REQ-PIPE-279 criterion 21). By recorded supply
id, never by physical name, so a table promoted out of staging between the
two runs is still the same supply.

NEVER A NON-ANSWER (criterion 6): a sibling that recorded nothing for the
check (its own table held, contested or refused), only a not-evaluated
record, or itself carried it, has no verdict to carry.

SIBLINGS ARE READ FROM THE RECORD (REQ-PIPE-279 criterion 22): the arrival
runs whose supplies were filed from one delivery with one receipt instant
(qa.supply_receipt, over qa.filing and qa.delivery_file), never parsed out of
run ids. STAGGERED FILES ARE NOT SIBLINGS (criterion 8): one delivery, two
receipt instants, and their two results genuinely differ.
"""
from __future__ import annotations

from qa_tools.common import qa_store

#: The tools whose checks can be carried - the scoped ones, the only ones
#: asked for a run's scope rather than the whole collection.
CARRIED_TOOLS = ("dbt", "soda", "datacontract")

#: The record keys that make a result a not-evaluated one rather than a
#: verdict on the data - each pseudo-tool's reason, a real tool's own, and
#: Evidently's (REQ-QAC-108 criterion 9). The dashboard build reads the
#: same keys (pipeline.build_dashboard_data._not_evaluated_reason).
NOT_EVALUATED_KEYS = ("unrunnable_reason", "held_reason", "not_evaluated_reason")


def not_evaluated_reason(record: dict) -> str | None:
    """Why a record's check could not be evaluated, or None for a verdict."""
    for key in NOT_EVALUATED_KEYS:
        if record.get(key):
            return record[key]
    if record.get("reference_not_evaluated"):
        return record.get("reference_reason") or "not evaluated"
    return None


def siblings(conn, run_id: str) -> list[str]:
    """The other arrival runs whose supplies were filed from `run_id`'s
    supply's delivery at its receipt instant, in the order they were opened
    (qa.run.run_seq) - none for a re-check, readers-only or knock-on run, a
    run that belongs to no supply, or one no sibling has been opened beside.
    An unopened sibling has evaluated nothing, so it is not one yet."""
    s = qa_store.SCHEMA
    return [row[0] for row in conn.execute(
        f'SELECT o.run_key FROM "{s}".run r '
        f'JOIN "{s}".supply_receipt me ON me.dataset_id = r.dataset_id '
        "AND me.supply_id = r.supply_id "
        f'JOIN "{s}".supply_receipt rc ON rc.delivery = me.delivery '
        "AND rc.received_instant = me.received_instant "
        f'JOIN "{s}".run o ON o.dataset_id = rc.dataset_id AND o.supply_id = rc.supply_id '
        "WHERE r.run_key = ? AND r.scope = 'arrival' AND o.scope = 'arrival' "
        "AND o.run_key <> r.run_key AND o.collection_id = r.collection_id "
        "AND o.run_seq IS NOT NULL ORDER BY o.run_seq", [run_id]).fetchall()]


def _reads_of(check_id: str, reads: dict[str, list[str]]) -> set[str] | None:
    """Every table a cross-table check reads: those it declares and its own
    dataset's, which it reads implicitly. None for a check that declares
    no reads - not a cross-table check."""
    from qa_tools.common import check_id as check_id_mod
    from qa_tools.common import hierarchy

    declared = reads.get(check_id) or []
    parsed = check_id_mod.try_parse(check_id)
    if not declared or parsed is None:
        return None
    return {*declared, hierarchy.dataset(parsed.dataset).table}


def _supply_read(res, logical: str) -> str | None:
    """The supply `logical` is read as in this run's resolution, or None
    where it is not read unambiguously - absent, held or contested."""
    if (logical not in res.resolved or logical in res.held
            or logical in res.ambiguous or logical in res.absent):
        return None
    return res.supply_of.get(logical)


def _evaluated_reads(conn, run_key: str, check_ids: set[str]) -> dict[str, dict]:
    """check id -> {table: the supply its result READ, or None} for each of
    `check_ids` that `run_key` recorded a VERDICT for, from a real tool - not
    a not-evaluated record, not a carried one. The newest result of a check
    within the run, as one run's reader takes it."""
    from qa_tools.common import qa_results_reader as reader

    if not check_ids:
        return {}
    cursor = conn.execute(
        f'SELECT * FROM "{qa_store.SCHEMA}".check_result_visible WHERE run_key = ? '
        "AND supply_state = ? AND tool = ANY(?) AND check_id = ANY(?) ORDER BY id",
        [run_key, qa_store.AGREED, list(CARRIED_TOOLS), sorted(check_ids)])
    columns = [d.name for d in cursor.description]
    rows = cursor.fetchall()
    ids = {row[columns.index("check_id")]: row[columns.index("id")] for row in rows}
    latest: dict[str, dict] = {}
    for record in reader.records_from(cursor.description, rows):
        latest[record["check_id"]] = record
    already = set(carried_of(conn, run_key))
    out: dict[str, dict] = {}
    for check, record in latest.items():
        if not_evaluated_reason(record) is not None or check in already:
            continue
        out[check] = {table: (supply if state == qa_store.READ and not contested else None)
                      for table, state, supply, contested in conn.execute(
                          f'SELECT logical_table, state, supply_id, contested '
                          f'FROM "{qa_store.SCHEMA}".check_read WHERE check_result_id = ?',
                          [ids[check]]).fetchall()}
    return out


def decide(conn, run_id: str, in_scope, reads: dict[str, list[str]]) -> dict[str, str]:
    """check id -> the sibling run whose verdict `run_id` carries, for every
    cross-table check in its scope that a sibling evaluated over the same
    supplies - the earliest-opened such sibling. Empty for a run with no
    siblings."""
    from qa_tools.common import check_id as check_id_mod
    from qa_tools.common import supply_db

    others = siblings(conn, run_id)
    if not others:
        return {}
    candidates: dict[str, set[str]] = {}
    for check, _tables in reads.items():
        parsed = check_id_mod.try_parse(check)
        if parsed is None or parsed.tool not in CARRIED_TOOLS or not in_scope(check):
            continue
        tables = _reads_of(check, reads)
        if tables:
            candidates[check] = tables
    if not candidates:
        return {}
    here = supply_db.resolution_for(conn, run_id)
    out: dict[str, str] = {}
    for sibling in others:
        open_ = {c for c in candidates if c not in out}
        if not open_:
            break
        for check, there in sorted(_evaluated_reads(conn, sibling, open_).items()):
            if all(_supply_read(here, t) is not None and _supply_read(here, t) == there.get(t)
                   for t in candidates[check]):
                out[check] = sibling
    return out


def record(conn, run_id: str, carried: dict[str, str]) -> None:
    """Record what `run_id` carries, replacing what was recorded for it -
    a run decided twice keeps its latest decision."""
    conn.execute(f'DELETE FROM "{qa_store.SCHEMA}".carried_check WHERE run_key = ?', [run_id])
    for check, from_run in sorted(carried.items()):
        conn.execute(f'INSERT INTO "{qa_store.SCHEMA}".carried_check '
                     "(run_key, check_id, from_run_key) VALUES (?, ?, ?)",
                     [run_id, check, from_run])


def carried_of(conn, run_id: str) -> dict[str, str]:
    """check id -> the run it was carried from, as recorded for `run_id`."""
    # NO try/except HERE: on a shared connection a failed statement aborts its
    # transaction. The table exists wherever ensure_schema has run, which
    # every write to the qa schema does first.
    rows = conn.execute(
        f'SELECT check_id, from_run_key FROM "{qa_store.SCHEMA}".carried_check '
        "WHERE run_key = ?", [run_id]).fetchall()
    return {c: f for c, f in rows}


def carried_for(run_id: str) -> dict[str, str]:
    """carried_of() on its own connection, for the scope rule."""
    from qa_tools.common import supply_db

    try:
        with supply_db.connect(read_only=True, label="mothman:carried") as conn:
            return carried_of(conn, run_id)
    except Exception:  # noqa: BLE001 - no database means nothing carried
        return {}


def records_for(conn, run_id: str) -> list[dict]:
    """The carried checks' verdicts, from the runs that evaluated them, as
    records the gate reads with `run_id`'s own (criterion 3). Each keeps its
    own run_key - the run that evaluated it - and is handed to `run_id`'s
    gate under `run_id`."""
    from qa_tools.common import qa_results_reader as reader

    out: list[dict] = []
    by_source: dict[str, list[str]] = {}
    for check, source in carried_of(conn, run_id).items():
        by_source.setdefault(source, []).append(check)
    for source, checks in sorted(by_source.items()):
        cursor = conn.execute(
            f'SELECT * FROM "{qa_store.SCHEMA}".check_result_visible WHERE run_key = ? '
            "AND supply_state = ? AND tool = ANY(?) AND check_id = ANY(?) ORDER BY id",
            [source, qa_store.AGREED, list(CARRIED_TOOLS), sorted(checks)])
        latest: dict[str, dict] = {}
        for record in reader._records(cursor, source):
            latest[record["check_id"]] = record
        for record in latest.values():
            out.append({**record, "run_id": run_id, "carried_from": source})
    return out


def decide_and_record(run_id: str, *, readable: bool = True) -> dict[str, str]:
    """Decide what `run_id` carries and record it - BEFORE its tools are
    asked for anything, which is what makes the record the one answer
    every later reader gets. A run that may not read its own table runs no
    tools at all and carries nothing."""
    from qa_tools.common import promotion, qa_results_writer, supply_db

    with supply_db.connect(label="mothman:carried") as conn:
        qa_store.ensure_schema(conn)
        carried = (decide(conn, run_id, qa_results_writer.base_scope_of_run(run_id),
                          promotion._declared_reads()) if readable else {})
        record(conn, run_id, carried)
    return carried


def describe(run_id: str, carried: dict[str, str]) -> str:
    """One line for the run's own output."""
    sources = sorted(set(carried.values()))
    return (f"{run_id}: {len(carried)} cross-table check(s) carried from "
            f"{', '.join(sources)} - the same supplies, evaluated once (REQ-PIPE-265)")
