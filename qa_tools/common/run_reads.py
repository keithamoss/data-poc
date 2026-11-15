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
    from asset_model import check_id as check_id_mod

    parsed = check_id_mod.try_parse(check_id)
    return parsed.collection if parsed is not None else None


def reads_for(collection_id: str) -> RunReads:
    """The tables a run of `collection_id` reads: its own, then every other
    collection's table one of its checks declares, sorted."""
    from asset_model import collections
    from asset_model import hierarchy
    from qa_tools.common import promotion

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
    from asset_model import hierarchy
    from qa_tools.common import promotion

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
    declares of ANOTHER collection's table names a table some dataset of the
    asset's hierarchy owns, and neither the declaring dataset nor the one it
    reads declares no calendar.

    ONE BASELINE PER ASSET (REQ-PIPE-345): every calendared dataset of an
    asset is on its one baseline, so two calendared datasets are always on
    the same calendar and there is no different-calendar case left to
    refuse or to record not applicable (REQ-PIPE-331 criterion 2 as amended
    by REQ-PIPE-345 removed calendar_differs). What is left is a dataset
    with no calendar on EITHER side (Keith, G2): it has no period to read or
    be read for, and refusing only the read side would let the other through
    in silence."""
    from asset_model import check_id as check_id_mod
    from asset_model import hierarchy, schedule
    from qa_tools.common import promotion

    if declared is None:
        declared = promotion._declared_reads()
    owners = {d.table: d for d in hierarchy.all_datasets()}

    def has_calendar(dataset_id):
        try:
            schedule.calendar_for_dataset(dataset_id, agreement)
        except schedule.NoCalendarAgreed:
            return False
        return True

    out = []
    for check_id, tables in sorted(declared.items()):
        parsed = check_id_mod.try_parse(check_id)
        if parsed is None:
            continue
        for table in tables:
            if table not in owners:
                # Naming the asset folder checked, and never looking in
                # another asset's (REQ-PIPE-364 criterion 4).
                from asset_model import assets

                out.append(f"{check_id} declares a read of {table!r}, which no dataset in "
                           f"the hierarchy owns ({assets.config_dir()}/data-asset.yaml; "
                           f"REQ-PIPE-331 criterion 2).")
                continue
            owner = owners[table]
            if owner.collection_id == parsed.collection:
                continue
            if not has_calendar(owner.dataset_id):
                out.append(f"{check_id} reads {table!r}, whose dataset {owner.dataset_id} "
                           f"names no calendar - it has no period to be read for "
                           f"(REQ-PIPE-331 criterion 2).")
            elif not has_calendar(parsed.dataset):
                out.append(f"{check_id} reads {table!r}, but its own dataset "
                           f"{parsed.dataset} declares no calendar - it has no period "
                           f"to read it for (REQ-PIPE-331 criterion 2).")
    return out


def unreadable_in(conn, collection_id: str, run_id: str) -> frozenset[str]:
    """Every table a run of `collection_id` reads - its own and every other
    collection's its checks declare - that has no view in the run's schema
    (criterion 8): what a runner leaves out, so a check reading an absent
    table of another collection is treated exactly as one reading an absent
    table of its own, never handed to its tool to raise."""
    from qa_tools.common import supply_db

    return frozenset(reads_for(collection_id).tables) - frozenset(
        supply_db.readable_in(conn, run_id))
