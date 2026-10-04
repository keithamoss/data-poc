"""What a one-file arrival's run reads (REQ-PIPE-105 criterion 5).

ONE FILE IS ONE ARRIVAL (criterion 1), so a run's own staged tables are
ONE table - and every cross-table check asks for six. This module is
what makes that viable rather than a broken pipeline: the run reads the
table its arrival carried from that arrival, and every OTHER table from
the version staged for the same PERIOD where exactly one is, falling
back to that period's promoted state where none is.

WHY IT RUNS AFTER FILING, NOT AT STAGING. A run's period is
`filing.period_of()`, and a supply is filed one arrival at a time in
receipt order because the slot it files to depends on what the arrival
before it promoted. The warehouse builders still give a run a view of
its own table at staging time; this REPLACES that schema once the
period is known. A supply with no filing - held, unfiled, a trial - is
left with what staging gave it (REQ-PIPE-079 criterion 9: no invented
period, no period-scoped run).

"STAGED FOR THE PERIOD" MEANS FILED TO IT AND STILL IN STAGING. Filing
says which period a supply claims; promotion MOVES a supply's tables out
of staging into the period's schema, so what is left in staging is
exactly what nobody has decided on. A supply staged for a DIFFERENT
period is never read, which is criterion 8 of REQ-PIPE-079 - no reading
across period schemas.

THE RUN'S OWN TABLE IS READ FROM ITS OWN ARRIVAL, always (criterion 5,
and criterion 6 as Keith amended it on the evening of 2026-10-02). It
is contested only where that one arrival carried two files for it. A
SIBLING with several versions staged for the period is contested for
the run reading it (criterion 8): the view falls through to the
period's promoted version and nothing chooses between them by arrival
time. An earlier reading, that any second staged version contested the
run's own table "however they arrived", left a correction beside a red
supply unchecked and unpromotable - 28 supplies in the regenerate - and
is recorded as rejected on REQ-PIPE-105.
"""
from __future__ import annotations

from collections.abc import Collection, Sequence

from qa_tools.common import period_schema, supply_db


def staged_for_period(conn, period: str, logical_names: Sequence[str], *,
                       staging: str,
                       loaded: frozenset[str] | None) -> dict[str, list[str]]:
    """Every physical table in `staging` whose supply is FILED to
    `period`, keyed by the logical name it claims.

    Joined on (dataset, arrival key) against `qa.filing`, because the
    supply id is filing's answer and the physical name is staging's -
    the arrival key is what both carry. The `#1` a held supply's id
    carries is stripped, and a held supply is never filed to a slot
    anyway, so it cannot appear here.

    The load-record gate applies as it does everywhere a check's view is
    built (REQ-PIPE-060 criterion 7): `loaded=None` skips it.
    """
    from qa_tools.common import filing, hierarchy, qa_store

    qa_store.ensure_schema(conn)
    wanted = set(logical_names)
    filed: set[tuple[str, str]] = set()
    for dataset_id, supply_id in conn.execute(
            f"SELECT dataset_id, supply_id FROM {filing.TABLE} WHERE slot = ?",
            [period]).fetchall():
        try:
            logical = hierarchy.dataset(dataset_id).table
        except hierarchy.UnknownDatasetError:
            continue
        if logical not in wanted or "@" not in supply_id:
            continue
        filed.add((logical, supply_id.rsplit("@", 1)[1].split("#", 1)[0]))

    found: dict[str, list[str]] = {name: [] for name in wanted}
    for logical, physicals in supply_db.candidates_in(
            conn, staging, sorted(wanted), loaded=loaded).items():
        for physical in physicals:
            parts = supply_db.split_staged(physical)
            if parts and (logical, parts[1]) in filed:
                found[logical].append(physical)
    return found


def build(conn, run_id: str, *, period: str, own_table: str, arrival_key: str,
          tables: Sequence[str], loaded: frozenset[str] | None,
          held: Collection[str] = ()) -> period_schema.PeriodResolution:
    """Replace this run's view schema with the period overlay, and
    record what it resolved.

    `tables` is every agreed logical table a check in this collection
    may read, `own_table` among them. Sample tables are not here: they
    have no period, and the caller adds them on top exactly as it did
    before (REQ-PIPE-106).

    `held` applies to the run's OWN table only, as it did at staging. A
    held supply has no filing, so it can never be staged-for-period for
    a sibling to read.
    """
    staging = supply_db.staging_schema_for(run_id)
    others = [t for t in tables if t != own_table]
    staged = staged_for_period(conn, period, others, staging=staging, loaded=loaded)

    # THE RUN'S OWN TABLE IS ITS OWN ARRIVAL'S, and nothing else staged
    # for the period competes with it (criterion 6 as amended 2026-10-02
    # evening). Two files in THIS arrival are contested; a correction
    # beside an earlier red supply is not - it is checked on its own
    # data, which is the only way it can ever be accepted.
    own = supply_db.candidates_in(conn, staging, [own_table], arrival=arrival_key,
                                   loaded=loaded).get(own_table) or []
    staged[own_table] = sorted(own)

    withheld = None
    if own_table in set(held) and own:
        # Same refusal create_run_views() makes: the held table is
        # sitting right there and is deliberately not read.
        withheld = own[0] if len(own) == 1 else ""
        staged[own_table] = []

    promoted = period_schema.promoted_in(conn, period, list(tables))
    if withheld is not None:
        # A held table falls through to nothing, not to the period: a
        # hold is about not knowing the period at all.
        promoted.pop(own_table, None)
    out = period_schema.create_overlay_views(conn, run_id, period, staged, promoted)
    if withheld is not None:
        out.resolution.held[own_table] = withheld
        if own_table in out.resolution.absent:
            out.resolution.absent.remove(own_table)
    return out


def name_held_siblings(conn, res: supply_db.Resolution, arrival) -> list[str]:
    """Say HELD, not absent, for a sibling whose supply came WITH this
    arrival and is held (REQ-PIPE-115 criterion 14).

    A held supply has no filing, so it is never staged for a period and
    its table reaches a sibling run exactly as a table that never
    arrived does - and the checks reading it then said "no filled slot"
    or "overdue", sending somebody after a supplier who had already sent
    the file. Keith, 2026-10-04 (option B): only for runs of arrivals
    received WITH the held supply - same delivery or same receipt
    instant. Every run while any hold for the table is outstanding would
    redden another quarter's checks for a file meant elsewhere.

    ONLY A TABLE THE RUN CANNOT READ. Where the period's promoted
    version is there to read, the check reads it, as REQ-PIPE-079
    criterion 12 lets a sibling do (PROVISIONAL, 2026-10-04 overnight).

    Moved into `held` in place, so held_blast_radius records it once,
    naming the supply, and unrunnable leaves it alone (criterion 15).
    Returns the tables moved.
    """
    from qa_tools.common import hierarchy, supply_holds

    if not res.absent:
        return []
    key = supply_db.arrival_segment(arrival.received_at)
    delivery = getattr(arrival, "delivery_name", None)
    moved = []
    for held in supply_holds.outstanding(conn):
        if not (supply_holds.arrival_key_of(held.supply_id) == key
                or (delivery and held.delivery == delivery)):
            continue
        try:
            table = hierarchy.dataset(held.dataset_id).table
        except Exception:  # noqa: BLE001 - a retired dataset reads as absent
            continue
        if table in res.absent:
            res.absent.remove(table)
            res.held[table] = held.supply_id
            moved.append(table)
    return moved


def _withhold_if_held(arrival, dataset_id: str, own_table: str, *,
                      dsn: str | None) -> None:
    """A HELD supply's run must not read its own table (REQ-PIPE-115
    criterion 5), whatever staging gave it.

    THE DEFECT THIS CLOSES: staging builds every run's views before
    filing raises the hold, and returning early here for a supply with
    no period left that view in place - so all four tools ran over a
    supply nobody had placed and recorded ordinary verdicts against it.
    The view is dropped and the table recorded as HELD, which is what
    the orchestrators read to run nothing.

    ONLY WHERE THIS ARRIVAL'S SUPPLY HAS AN OPEN HOLD. An unfiled supply
    with no hold - a trial - keeps what staging gave it, exactly as
    before (REQ-PIPE-079 criterion 9).
    """
    from qa_tools.common import supply_holds

    key = supply_db.arrival_segment(arrival.received_at)
    conn = supply_db.connect(dsn=dsn, label="mothman:period-overlay")
    try:
        if not any(supply_holds.arrival_key_of(h.supply_id) == key
                   for h in supply_holds.outstanding(conn, dataset_id=dataset_id)):
            return
        res = supply_db.resolution_for(conn, arrival.run_id)
        physical = res.resolved.pop(own_table, None)
        if physical is None:
            physical = (res.ambiguous.pop(own_table, None) or [""])[0]
        if own_table in res.absent:
            res.absent.remove(own_table)
        res.held[own_table] = physical
        conn.execute(f'DROP VIEW IF EXISTS "{supply_db.run_schema(arrival.run_id)}".'
                     f'"{own_table}"')
        supply_db.record_resolution(conn, res)
    finally:
        conn.close()


def own_table_contested(res: supply_db.Resolution, own_table: str) -> bool:
    """Whether this run's own table is contested - REQ-PIPE-079
    criterion 13's trigger for withholding its own checks."""
    return own_table in res.ambiguous


def rebuild_for_arrival(arrival, *, tables: Sequence[str],
                        dsn: str | None = None) -> period_schema.PeriodResolution | None:
    """The batch's one call: after an arrival is filed, give its run
    the period overlay and record what it read.

    Returns None - and leaves the staging-time views alone - where the
    arrival's supply was filed to no period, which is the held and the
    unfiled case alike (REQ-PIPE-079 criterion 9).

    `tables` is the collection's logical tables. Those with no agreed
    calendar are SAMPLE data and are added from the sample schema on
    top, newest version, exactly as the staging-time build does: sample
    data has no arrival or period that matters (REQ-PIPE-106).
    """
    from qa_tools.common import (filing, hierarchy, load_log, sample_data,
                                  supply_holds, trial)

    (dataset_id,) = tuple(arrival.files_by_dataset)
    period = filing.period_of(dataset_id, arrival.received_at)
    own_table = hierarchy.dataset(dataset_id).table
    if not period:
        _withhold_if_held(arrival, dataset_id, own_table, dsn=dsn)
        return None
    sample = [t for t in tables
              if sample_data.is_sample(hierarchy.dataset_for_table(t).dataset_id)]
    agreed = [t for t in tables if t not in sample]
    trial_scope = trial.scope_for(arrival.run_id)
    loaded = load_log.loaded_tables(trial_scope)

    conn = supply_db.connect(dsn=dsn, label="mothman:period-overlay")
    try:
        out = build(conn, arrival.run_id, period=period, own_table=own_table,
                    arrival_key=supply_db.arrival_segment(arrival.received_at),
                    tables=agreed, loaded=loaded,
                    held=supply_holds.held_tables(
                        conn, arrival_key=supply_db.arrival_segment(arrival.received_at)))
        if sample:
            found = supply_db.candidates_in(conn, sample_data.SCHEMA, sample,
                                             loaded=loaded)
            newest = {logical: [period_schema.newest(versions)]
                      for logical, versions in found.items()
                      if period_schema.newest(versions) is not None}
            supply_db.add_run_views(conn, arrival.run_id, newest,
                                     sample_data.SCHEMA, out.resolution)
        name_held_siblings(conn, out.resolution, arrival)
        supply_db.record_resolution(conn, out.resolution)
    finally:
        conn.close()
    return out
