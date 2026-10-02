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

THE RUN'S OWN TABLE IS CONTESTED where another version is staged for
the same period (criterion 6, settled with Keith 2026-10-02 over
criterion 5's "read from that arrival"): several files claiming one
dataset for one period are contested however they arrived, so the view
falls through to the period's promoted version, `ambiguous` records the
contest, and the table's own checks and its promotion are withheld
elsewhere. That is the cost Keith accepted on 2026-09-28 - a correction
landing beside an unpromoted red supply waits for a person to reject
the earlier one.
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

    own = supply_db.candidates_in(conn, staging, [own_table], arrival=arrival_key,
                                   loaded=loaded).get(own_table) or []
    # CRITERION 6: anything ELSE staged for this period under the same
    # name makes the run's own table contested, not just a second file
    # in this arrival.
    rivals = staged_for_period(conn, period, [own_table], staging=staging,
                                loaded=loaded).get(own_table) or []
    staged[own_table] = sorted(set(own) | set(rivals))

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
    if not period:
        return None
    own_table = hierarchy.dataset(dataset_id).table
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
                    held=supply_holds.held_tables(conn))
        if sample:
            found = supply_db.candidates_in(conn, sample_data.SCHEMA, sample,
                                             loaded=loaded)
            newest = {logical: [period_schema.newest(versions)]
                      for logical, versions in found.items()
                      if period_schema.newest(versions) is not None}
            supply_db.add_run_views(conn, arrival.run_id, newest,
                                     sample_data.SCHEMA, out.resolution)
        supply_db.record_resolution(conn, out.resolution)
    finally:
        conn.close()
    return out
