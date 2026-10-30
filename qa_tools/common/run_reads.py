"""Which tables a collection's run reads, and from where (REQ-PIPE-331).

THE ONE ANSWER every place that builds, re-checks or gates a run asks
(criterion 3): the staging-time view build, period_overlay's rebuild after
filing, recheck.execute and the gate's warehouse view. Four callers each
working out their own list is how a run and its gate come to disagree about
what was read (architect M1).

A collection's run reads its OWN collection's tables as it always has -
staged siblings for its period, else the period's - and, where an active
check declares a table of ANOTHER collection in reads_tables, that table
from the period's WAREHOUSE ONLY (Keith, 2026-10-28): promoted, inherited or
substituted, never staged. Generic - nothing here names a collection.

CONFIGURATION ONLY: the hierarchy and the working tree's check declarations.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunReads:
    own: tuple[str, ...]          # the collection's own logical tables
    foreign: tuple[str, ...]      # other collections' tables its checks declare

    @property
    def tables(self) -> list[str]:
        return [*self.own, *self.foreign]


def _collection_of_check(check_id: str) -> str | None:
    from qa_tools.common import check_id as check_id_mod

    parsed = check_id_mod.try_parse(check_id)
    return parsed.collection if parsed is not None else None


def reads_for(collection_id: str) -> RunReads:
    """The tables a run of `collection_id` reads: its own, then every other
    collection's table one of its checks declares, sorted."""
    from qa_tools import collections
    from qa_tools.common import hierarchy, promotion

    own = tuple(d.table for d in collections.by_id(collection_id).datasets)
    known = {d.table for d in hierarchy.all_datasets()}
    foreign = set()
    for check_id, tables in promotion._declared_reads().items():
        if _collection_of_check(check_id) != collection_id:
            continue
        foreign.update(t for t in tables if t not in own and t in known)
    return RunReads(own=own, foreign=tuple(sorted(foreign)))


def foreign_readers(table: str) -> list[str]:
    """Every collection one of whose checks declares a read of `table`, a
    table of another collection - the readers a move of `table`'s supply
    re-evaluates (criterion 5)."""
    from qa_tools.common import hierarchy, promotion

    try:
        owner = hierarchy.dataset_for_table(table).collection_id
    except Exception:  # noqa: BLE001 - not one of ours has no readers
        return []
    out = set()
    for check_id, tables in promotion._declared_reads().items():
        coll = _collection_of_check(check_id)
        if coll and coll != owner and table in tables:
            out.add(coll)
    return sorted(out)


def declaration_problems(declared: dict[str, list[str]] | None = None,
                         agreement=None) -> list[str]:
    """REQ-PIPE-331 criterion 2, from configuration: every read a check
    declares of ANOTHER collection's table names a table some dataset owns,
    on the same calendar as the declaring dataset, which names one.

    A dataset names one calendar for its whole life (contract/calendar.yaml
    versions the calendar's rounds, not which calendar a dataset is on), so
    two datasets are on the same calendar in every period or in none - and
    a pair on different calendars is refused here outright, which leaves no
    period in which they could differ (the not-applicable case of the same
    criterion has nothing to record until a dataset's calendar is itself
    versioned)."""
    from qa_tools.common import check_id as check_id_mod
    from qa_tools.common import hierarchy, promotion, schedule

    if declared is None:
        declared = promotion._declared_reads()
    owners = {d.table: d for d in hierarchy.all_datasets()}

    def calendar_name(dataset_id):
        try:
            return schedule.calendar_for_dataset(dataset_id, agreement).name
        except schedule.NoCalendarAgreed:
            return None

    out = []
    for check_id, tables in sorted(declared.items()):
        parsed = check_id_mod.try_parse(check_id)
        if parsed is None:
            continue
        for table in tables:
            if table not in owners:
                out.append(f"{check_id} declares a read of {table!r}, which no dataset in "
                           f"the hierarchy owns (REQ-PIPE-331 criterion 2).")
                continue
            owner = owners[table]
            if owner.collection_id == parsed.collection:
                continue
            mine, theirs = calendar_name(parsed.dataset), calendar_name(owner.dataset_id)
            if theirs is None:
                out.append(f"{check_id} reads {table!r}, whose dataset {owner.dataset_id} "
                           f"names no calendar - it has no period to be read for "
                           f"(REQ-PIPE-331 criterion 2).")
            elif mine != theirs:
                out.append(f"{check_id} reads {table!r}, whose dataset {owner.dataset_id} is "
                           f"on the {theirs} calendar and never on {parsed.dataset}'s "
                           f"{mine} calendar - a check reads only its own period "
                           f"(REQ-PIPE-331 criterion 2).")
    return out
