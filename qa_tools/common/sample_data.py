"""Data for a dataset nobody has agreed a delivery schedule for
(REQ-PIPE-106) - sample data somebody is developing checks against, or a
one-off extraction for a project that will never have a cadence.

WHY THIS MODULE EXISTS RATHER THAN A FLAG PASSED AROUND. Criterion 5 asks
for the exclusion to hold BY CONSTRUCTION, and criterion 10 asks the QA
record to stay distinguishable from real quality history. Both are
properties of the SYSTEM rather than of a call site, so both are derived
here from configuration - the `no_calendar:` declaration a dataset makes
in `contract/data-asset.yaml` - and every caller asks rather than
remembers. A `sample=True` argument threaded through eight run_*.py
modules is the shape that fails in the quiet direction: one call site
forgets, and check-development verdicts start counting toward a real
dataset's quality history with nothing to notice it.

TWO MECHANISMS, ONE SOURCE. The DATA goes to a schema of its own
(`supply_db.SAMPLE_SCHEMA`), which is what makes it invisible to every
period, slot, lateness and promotion computation - those read staging and
the period schemas, and nothing here teaches them a new exception. The
RECORD carries `supply_state = in-development`, which is what keeps it out
of every read a viewer would take as real history, since `qa_store`'s
reads default to AGREED and a caller has to ask for the other.

NOTHING HERE IS CACHED, deliberately. It asks the hierarchy and the
agreement (through `schedule`), which keep what they build keyed on their
files' content (REQ-PIPE-254) - so an edited or swapped file is seen on the
next call with nothing to clear, and a cache of its own here would be one
more value that could answer for a file as it used to read.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from asset_model import hierarchy, schedule
from qa_tools.common import qa_store, supply_db

#: Where this data lands. Named here as well as in supply_db so a reader
#: of this module does not have to go and look - it is the same schema.
SCHEMA = supply_db.SAMPLE_SCHEMA


def is_sample(dataset_id: str) -> bool:
    """Whether this dataset has declared that it has no calendar.

    True for BOTH kinds - `not-yet-agreed` and `never` - because this is
    the ROUTING question (REQ-PIPE-438's MAINTAINABILITY NFR): neither has a
    period, so both are filed to none (REQ-PIPE-434) and staged into the
    no-period schema. Whether the RECORD counts as quality history is a
    different question, supply_state()'s, and no caller asks one for the
    other.
    """
    return schedule.no_calendar(dataset_id) is not None


def sample_dataset_ids() -> frozenset[str]:
    """Every dataset in the asset that has no calendar.

    READ FROM THE HIERARCHY rather than from a list somebody maintains
    beside it, which is criterion 12 falling out rather than being
    implemented: any number of these, in one collection or across
    several, with nothing here counting them.
    """
    return frozenset(d.dataset_id for d in hierarchy.all_datasets()
                     if schedule.no_calendar(d.dataset_id) is not None)


@dataclass(frozen=True)
class Uncounted:
    """Which datasets' results are NOT agreed quality history (REQ-PIPE-438):
    those declaring `no_calendar: not-yet-agreed`, and those declared
    `derived: true`. A `never` dataset that is not derived is counted.

    THE COUNTED QUESTION, kept apart from is_sample()'s ROUTING question
    (REQ-PIPE-438's MAINTAINABILITY NFR): both no_calendar values route to
    the no-period schema, and only these two kinds are recorded in
    development. A hoist, not a second source: built from the declarations
    by uncounted(), and passed by a caller deciding thousands of records in
    one loop rather than rebuilt per record."""

    not_yet_agreed: frozenset[str]
    derived: frozenset[str]

    def __contains__(self, dataset_id: str) -> bool:
        return dataset_id in self.not_yet_agreed or dataset_id in self.derived


def uncounted() -> Uncounted:
    """Every dataset in the asset whose results are recorded in development."""
    nya, derived = set(), set()
    for d in hierarchy.all_datasets():
        kind = schedule.no_calendar(d.dataset_id)
        if kind == schedule.NOT_YET_AGREED:
            nya.add(d.dataset_id)
        if kind is not None and schedule.is_derived(d.dataset_id):
            derived.add(d.dataset_id)
    return Uncounted(frozenset(nya), frozenset(derived))


def supply_state(dataset_id: str | None, *, kinds: Uncounted | None = None) -> str:
    """Which `supply_state` a result about this dataset is recorded under.

    IN DEVELOPMENT FOR `not-yet-agreed` AND FOR A DERIVED PRODUCT, AGREED
    OTHERWISE (REQ-PIPE-438 criterion 2) - a `never` dataset's results are
    real quality history, because a one-off's QA is the deliverable (Keith,
    2026-11-21, Q4.1 (a)).

    A dataset id this asset does not define is AGREED rather than an
    error, and the direction is deliberate: the risk this whole mechanism
    guards against is check development counting as real, and an id that is
    not a configured dataset is not that. A genuinely unknown dataset is a
    hierarchy error, reported by the hierarchy gate where it means
    something, not inferred here from a QA write.

    `kinds` IS A HOIST, NOT A SECOND SOURCE OF TRUTH: see Uncounted.
    """
    if not dataset_id:
        return qa_store.AGREED
    found = uncounted() if kinds is None else kinds
    return qa_store.IN_DEVELOPMENT if dataset_id in found else qa_store.AGREED


def state_for_participants(dataset_ids: Iterable[str], *,
                           kinds: Uncounted | None = None) -> str:
    """The state a check spanning these datasets is recorded under.

    IN DEVELOPMENT IF ANY PARTICIPANT IS `not-yet-agreed` (REQ-PIPE-106
    criterion 15), not only if all of them are. A mixed cross-table check - a
    new dataset joining an existing collection, which is arguably the
    strongest reason to develop checks early - is allowed (criterion 14) and
    must not be able to move the agreed dataset's verdict. Recording the whole
    result as in-development is what makes that true by construction: the
    agreed dataset's own page reads AGREED results, and this is not one.

    A DERIVED PRODUCT DOES NOT MAKE IT IN DEVELOPMENT (REQ-PIPE-438 criterion
    4, Keith 2026-11-21, round 5 Q3 (a)): a check over a derived and a counted
    table is recorded AGREED and counts on the counted side; it is shared
    with the derived product too and left out of that one's status by the
    dashboard build. Only where EVERY participant is derived did nothing
    count it, so it is in development.
    """
    found = uncounted() if kinds is None else kinds
    ids = list(dataset_ids)
    if any(d in found.not_yet_agreed for d in ids):
        return qa_store.IN_DEVELOPMENT
    if ids and all(d in found.derived for d in ids):
        return qa_store.IN_DEVELOPMENT
    return qa_store.AGREED


def is_sample_table(table: str) -> bool:
    """Whether the dataset that owns this PHYSICAL TABLE has no calendar.

    A DATASET ID AND A TABLE NAME ARE NOT THE SAME STRING - "cp-clients"
    against "cp_clients" - and this project has already shipped one bug
    from treating them as interchangeable (tables_read.attach, where a
    check recorded its own table as something it read). The staging path
    knows the table for certain and the dataset id only sometimes, so it
    asks this rather than passing whichever it has.

    A TABLE NOTHING MAPS IS NOT SAMPLE, the same direction supply_state()
    takes and for the same reason: an unresolvable name is the hierarchy
    gate's to report, and reading it as calendar-less here would divert a
    real supply into the sample schema over a typo.
    """
    try:
        dataset_id = hierarchy.dataset_for_table(table).dataset_id
    except Exception:  # noqa: BLE001 - see the docstring
        return False
    return is_sample(dataset_id)


def ensure_schema_for_table(conn, run_id: str, table: str) -> str:
    """ensure_schema_for(), asked about a table rather than a dataset id.

    What the two staging paths actually call, because `table` is the one
    of the two they always have unambiguously - see is_sample_table().
    """
    if is_sample_table(table):
        supply_db.create_if_absent(conn, f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')
        return SCHEMA
    return supply_db.ensure_staging(conn, run_id)


def schema_for(run_id: str, dataset_id: str | None) -> str:
    """Which schema this dataset's arrival stages into.

    THE SAMPLE SCHEMA WINS OVER A TRIAL'S OWN, and the order is worth
    stating because both are "not shared staging". A trial gets a schema
    named for the run so that declining to keep a check leaves nothing
    behind; sample data is not a trial - it is kept, deliberately, until a
    person discards it (criterion 18) - so a trial over a calendar-less
    dataset would be a contradiction rather than a case to handle. It
    cannot arise today: a trial is a person checking one arrival, and an
    arrival for a calendar-less dataset is sample data whichever way it
    came in.
    """
    if dataset_id and is_sample(dataset_id):
        return SCHEMA
    return supply_db.staging_schema_for(run_id)


def ensure_schema_for(conn, run_id: str, dataset_id: str | None) -> str:
    """schema_for(), with the schema brought into existence.

    `sample` is created by `supply_db.ensure_schemas()` alongside staging
    and rejected, so this only ever has to create a trial's own - which is
    why it delegates rather than repeating the CREATE.
    """
    if dataset_id and is_sample(dataset_id):
        supply_db.create_if_absent(conn, f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')
        return SCHEMA
    return supply_db.ensure_staging(conn, run_id)


def staged_tables(conn, dataset_id: str) -> list[str]:
    """Every physical table this dataset has in the sample schema.

    Matched by the LOGICAL half of the staged name rather than by a
    prefix, because `supply_db.split_staged()` is the one thing that knows
    how a physical name decomposes - and a `LIKE 'cp_carers%'` would also
    match a table for a dataset called `cp_carers_history`.
    """
    table = hierarchy.dataset(dataset_id).table
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
        [SCHEMA]).fetchall()
    out = []
    for (physical,) in rows:
        parts = supply_db.split_staged(physical)
        if parts is not None and parts[0] == table:
            out.append(physical)
    return sorted(out)


def discard(conn, dataset_id: str) -> list[str]:
    """Remove this dataset's pre-graduation data. Returns what was dropped.

    ONLY EVER CALLED BY A PERSON, from `mothman supply discard-sample`
    (criteria 17 and 18). Nothing in the pipeline calls this: not
    graduation, not a schedule, not as a side effect of anything else -
    Keith's own condition when he settled the fork, and the half a bare
    "discard" would have lost. Graduation and discarding are two acts, and
    a dataset growing up destroys nothing on its own.

    `tests/test_sample_data.py` asserts that constraint against the real
    tree rather than trusting this docstring, because a docstring is not a
    gate.

    CASCADE, for the reason `build_cp_warehouses` already gives: a run's
    view schema holds views onto these tables, and PostgreSQL refuses to
    drop a table those depend on. A view onto data a person has just
    discarded resolves to nothing anyone should read.
    """
    dropped = staged_tables(conn, dataset_id)
    for physical in dropped:
        conn.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."{physical}" CASCADE')
    return dropped


def newest(physical_names: Sequence[str]) -> str | None:
    """The newest of several versions of one SAMPLE table (REQ-PIPE-106).

    MOVED HERE FROM period_schema (REQ-PIPE-128 NFR 6): a period holds one
    version of each table and ranks nothing, but the sample schema keeps
    every version a run staged, and the newest is the one a check
    developed against it should read. Ordered by
    the ARRIVAL KEY the physical name carries, then by ordinal - not by
    the raw string, because a name without an ordinal must sort before
    the same name with one rather than lexically among them.

    Returns None for no candidates at all, which callers must treat as
    absence rather than as an error: absence is an ordinary state here
    and has its own criterion.
    """
    best, best_key = None, None
    for physical in physical_names:
        parts = supply_db.split_staged(physical)
        if parts is None:
            # A name this project did not mint. It cannot be ordered
            # against the others, so it never wins - being wrong about
            # WHICH version is read is the one outcome worth avoiding.
            continue
        _logical, arrival, ordinal = parts
        key = (arrival, ordinal or "")
        if best_key is None or key > best_key:
            best, best_key = physical, key
    return best
