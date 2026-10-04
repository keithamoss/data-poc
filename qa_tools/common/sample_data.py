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

NOTHING HERE IS CACHED, deliberately. It reads `schedule`, which caches
the parsed asset itself - so adding a second cache layer would be a second
thing a test fixture has to clear, and this project has already been bitten
by exactly that: three `lru_cache`es hold the parsed `data-asset.yaml`, and
missing one makes a fixture silently test the real asset.
"""
from __future__ import annotations

from typing import Iterable

from qa_tools.common import hierarchy, qa_store, schedule, supply_db

#: Where this data lands. Named here as well as in supply_db so a reader
#: of this module does not have to go and look - it is the same schema.
SCHEMA = supply_db.SAMPLE_SCHEMA


def is_sample(dataset_id: str) -> bool:
    """Whether this dataset has declared that it has no calendar.

    True for BOTH kinds - `not-yet-agreed` and `never` - because
    everything this module does is the same for both. Which kind it is
    matters to a person reading the dashboard (criterion 3) and not to
    where the data goes or how the record is keyed.
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


def supply_state(dataset_id: str | None, *,
                 sample_ids: frozenset[str] | None = None) -> str:
    """Which `supply_state` a result about this dataset is recorded under.

    A dataset id this asset does not define is AGREED rather than an
    error, and the direction is deliberate: the risk this whole mechanism
    guards against is sample data counting as real, and an id that is not
    a configured calendar-less dataset is not sample data. A genuinely
    unknown dataset is a hierarchy error, reported by the hierarchy gate
    where it means something, not inferred here from a QA write.

    `sample_ids` IS A HOIST, NOT A SECOND SOURCE OF TRUTH. A caller
    deciding this for thousands of records in one loop passes
    sample_dataset_ids() once rather than having it rebuilt per record -
    measured at ~1.6M frozenset constructions across one bootstrap
    otherwise. It is the same set either way, which is the point: the
    alternative was the caller inlining the membership test, and then the
    rule lives in two places.
    """
    if not dataset_id:
        return qa_store.AGREED
    ids = sample_dataset_ids() if sample_ids is None else sample_ids
    return qa_store.IN_DEVELOPMENT if dataset_id in ids else qa_store.AGREED


def state_for_participants(dataset_ids: Iterable[str], *,
                           sample_ids: frozenset[str] | None = None) -> str:
    """The state a check spanning these datasets is recorded under.

    IN-DEVELOPMENT IF ANY PARTICIPANT HAS NO CALENDAR (criterion 15), not
    only if all of them do. A mixed cross-table check - a new dataset
    joining an existing collection, which is arguably the strongest reason
    to develop checks early - is allowed (criterion 14) and must not be
    able to move the agreed dataset's verdict. Recording the whole result
    as in-development is what makes that true by construction: the agreed
    dataset's own page reads AGREED results, and this is not one.
    """
    ids = sample_dataset_ids() if sample_ids is None else sample_ids
    return (qa_store.IN_DEVELOPMENT if any(d in ids for d in dataset_ids)
            else qa_store.AGREED)


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
