"""A check somebody ran without keeping it (REQ-PIPE-103).

WHAT A TRIAL IS. An operator hands `mothman` a file - by path, by
folder, by S3 key - and is asked whether to keep the check. Saying yes
files the supply as a real delivery and it proceeds as an arrival like
any other, with a run id from recognition and a staged table named for
its receipt instant. Saying no gives a TRIAL: the same four real tools
run against the same real rows and report the same verdicts, and
nothing survives the command.

IT IS CALLED A TRIAL AND NOT A DRY RUN, deliberately. A dry run goes
through the motions without doing the thing; this does the thing in
full and declines to write it down. Nor "ad-hoc", which was the old
name and described a side channel that no longer exists - see
REQ-PIPE-103's own decisions.

NOTHING SURVIVES IS STRICTER THAN A RUN ALREADY WAS, which is the
whole substance of this module. A run discards its view schema and
dbt's when it finishes (REQ-PIPE-068), but STAGED TABLES ARE PERMANENT
BY DESIGN - staging only ever grows, one physical table per arrival,
because that is the history a read-the-newest rule exists for. Right
for a supply that really arrived; exactly wrong for one nobody
accepted.

SO A TRIAL NEVER WRITES INTO SHARED STAGING AT ALL. Everything it
touches goes into schemas of its own - `trial_<stamp>` for its
supplies, `qa_trial_<stamp>` for its views, `dbt_trial_<stamp>` for
dbt's models - and the tidy-up drops all of them in ONE transaction.
PostgreSQL has transactional DDL, which is what turns the guarantee
from "a walk that ought to finish" into either-all-or-none.

WHAT IS HONESTLY NOT GUARANTEED: `kill -9` between staging and the
tidy-up still leaves schemas behind, because no in-process mechanism
survives the process. What the design buys is that whatever is left
is identifiable from its name alone, sits nowhere near real supplies,
and is cleared by `mothman supply tidy` without anyone having to work
out which tables belonged to what.
"""
from __future__ import annotations

from datetime import datetime, timezone

from qa_tools.common import qa_store, supply_db

#: Prefix for a run nobody kept. supply_db owns the constant because
#: staging_schema_for() has to recognise one without importing this
#: module; it is re-exported here so callers have one obvious home.
TRIAL_PREFIX = supply_db.TRIAL_SCHEMA_PREFIX.rstrip("_")


def trial_run_id(reference: bool = False) -> str:
    """A run id for a check that will not be filed.

    THE CLOCK AND NOTHING ELSE. The predecessor built this out of the
    supplied file's own name, so a human skimming committed history
    could see which file a run came from - and a trial never reaches
    committed history, so it has nothing to carry. Dropping the stem
    also ends the duplication Keith noticed, where a staged table read
    `birth_registrations__adhoc_birth_registrat_...` because our own
    generated filenames happen to start with the table name.

    MICROSECONDS, not seconds. Second resolution was enough only while
    the filename carried the distinctness; without it, two trials
    started in the same second would be one run.

    `reference=True` gives the second run a trial needs - Evidently
    compares this supply against a previous one, and under a trial
    that previous one has to be staged somewhere disposable too. It
    is `trial_ref_...` rather than `ref_trial_...` on purpose: EVERY
    schema a trial creates then begins `trial_`, so one prefix finds
    all of them and the sweep needs no second pattern.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    middle = "ref_" if reference else ""
    return supply_db.normalise_ident_part(f"{TRIAL_PREFIX}_{middle}{stamp}")


def is_trial(run_id: str) -> bool:
    """Is this the id of a run nobody kept? Reads the id rather than
    asking a caller to remember - see supply_db.is_trial_run()."""
    return supply_db.is_trial_run(run_id)


def scope_for(run_id: str) -> str | None:
    """The scope a run's load records are written under.

    A REAL ARRIVAL'S ARE WRITTEN PLAINLY - `None`, meaning everybody
    sees them. A TRIAL'S CARRY ITS OWN RUN ID, because criterion 2 says
    a trial writes nothing that outlives the command and a load record
    is a record.

    THEY ARE WRITTEN RATHER THAN SKIPPED, which is the part worth
    explaining. The load record is not bookkeeping a trial could do
    without: it is the gate that decides which staged tables a run's
    views may resolve (REQ-PIPE-060 criterion 7 - physical presence is
    not readability). Skipping it would mean either a trial whose
    views resolve nothing, or a trial running under a weaker rule than
    a real run, and a trial that checks something slightly different
    from the real thing is not worth having.

    DERIVED FROM THE RUN ID rather than passed in, for the reason
    supply_db.is_trial_run() gives: a flag travelling beside the id
    through a dozen call sites is a flag one of them forgets.

    IT USED TO BE A DIRECTORY (`log_dir`), disposable because it sat
    outside the committed tree. A column is better for one specific
    reason rather than tidiness: `discard()` now removes the records in
    the same transaction that drops the schemas, so "a trial leaves
    nothing" is one atomic act instead of a DROP plus an rmtree that
    could half-happen.
    """
    return run_id if is_trial(run_id) else None

def schemas_of(conn, run_id: str) -> list[str]:
    """Every schema this trial actually has in the database right now.

    Derived from the run id, then filtered by what exists, so it is
    equally the answer to "did the tidy-up work" and "what is there to
    tidy". A trial that failed before staging owns nothing and gets an
    empty list.
    """
    if not is_trial(run_id):
        return []
    mine = {
        supply_db.staging_schema_for(run_id),
        supply_db.run_schema(run_id),
        supply_db.dbt_schema(run_id),
    }
    # DBT MAKES TWO SCHEMAS PER RUN, not one - `--store-failures` puts
    # each failing test's offending rows in `<target>_audit`.
    # Matched EXACTLY, so one trial cannot take a longer-named sibling's
    # (or a re-run's, REQ-PIPE-140) with it.
    mine.add(supply_db.dbt_audit_schema(run_id))
    present = supply_db.schemas_with_prefix(conn, supply_db.TRIAL_SCHEMA_PREFIX)
    present += supply_db.schemas_with_prefix(conn, supply_db.RUN_SCHEMA_PREFIX
                                             + supply_db.TRIAL_SCHEMA_PREFIX)
    present += supply_db.schemas_with_prefix(conn, supply_db.DBT_SCHEMA_PREFIX
                                             + supply_db.TRIAL_SCHEMA_PREFIX)
    return sorted(mine & set(present))


def orphan_schemas(conn) -> list[str]:
    """Every trial schema in the database, whoever it belongs to.

    WHAT A SWEEP CAN SEE AND WHAT IT CANNOT. A trial running right now
    in another process is indistinguishable from one a crash left
    behind - there is no record to consult, which is the point of a
    trial. So this LISTS rather than drops, and `mothman supply tidy`
    shows the list and asks, exactly as it does for orphaned run
    schemas.
    """
    seen = []
    for prefix in (supply_db.TRIAL_SCHEMA_PREFIX,
                   supply_db.RUN_SCHEMA_PREFIX + supply_db.TRIAL_SCHEMA_PREFIX,
                   supply_db.DBT_SCHEMA_PREFIX + supply_db.TRIAL_SCHEMA_PREFIX):
        seen += supply_db.schemas_with_prefix(conn, prefix)
    return sorted(set(seen))


def discard(conn, run_id: str) -> list[str]:
    """Remove everything this trial put in the database.

    ONE TRANSACTION, which is the difference between a guarantee and
    an intention. PostgreSQL's DDL is transactional, so either every
    schema goes or none does and the next `mothman supply tidy` finds
    them together - there is no half-cleared state for anyone to
    puzzle over. The connection is autocommit, so the transaction is
    opened explicitly here rather than inherited.

    Returns what it dropped. Discarding a trial that staged nothing is
    an ordinary no-op: a trial that failed before staging still
    reaches its own tidy-up, and must not turn one failure into two.

    IT CANNOT TOUCH A REAL SUPPLY, and not because it is careful -
    because a trial never writes into shared staging, so there is
    nothing of anyone else's inside the schemas it drops.
    """
    if not is_trial(run_id):
        raise supply_db.SupplyDbError(
            f"{run_id!r} is not a trial - refusing to discard a run that "
            "was kept")
    # Cheap once the schema exists - see qa_store.ensure_schema's own
    # version check - and needed because a trial can be discarded by a
    # `mothman supply tidy` in a process that has written nothing.
    qa_store.ensure_schema(conn)
    mine = schemas_of(conn, run_id)
    # THE LOAD RECORDS GO WITH THE SCHEMAS, inside the one transaction -
    # which is the whole reason they became a column rather than staying
    # a directory. A DROP that committed followed by an rmtree that did
    # not is a half-discarded trial; this cannot be one.
    with conn.raw.transaction():
        for schema in mine:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.execute(
            f'DELETE FROM "{qa_store.SCHEMA}".load_outcome WHERE trial_run_id = ?',
            [run_id])
        # ITS FILE-CHECK RESULTS GO TOO, and the run they registered when
        # that is all the run holds (post-build-review #118 D-C): staging a
        # reference run registered a qa.run that nothing ever completed, so
        # it was listed among the crashed runs forever, its results pointing
        # at load records deleted just above. A trial whose own checks were
        # recorded keeps them - only what screening added is undone.
        conn.execute(
            f"DELETE FROM \"{qa_store.SCHEMA}\".check_result WHERE run_key = ? AND tool = 'file'",
            [run_id])
        conn.execute(
            f'DELETE FROM "{qa_store.SCHEMA}".run r WHERE r.run_key = ? '
            f"AND r.completed_at IS NULL AND NOT EXISTS (SELECT 1 FROM "
            f'"{qa_store.SCHEMA}".check_result c WHERE c.run_key = r.run_key)',
            [run_id])
    return mine
