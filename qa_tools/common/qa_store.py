"""QA results in the database (REQ-PIPE-089).

WHAT THIS REPLACES. Until now every QA run wrote JSON files under
`qa_results/<agency>/<collection>/<dataset>/<run_id>/<tool>.json`, and
those files were COMMITTED - the durable record of every check this
pipeline ever ran, potentially spanning years. That made the repository
hold state as well as configuration, which is the thing Keith settled
against on 2026-09-27: "the repository only contains configuration, not
actual state, no state at all."

WHY A DATABASE IS BETTER HERE, beyond tidiness. The question this history
exists to answer is "what has this check done over time", and a file tree
can only answer it by being walked in full. One index turns the same
question into a WHERE clause. Retention also becomes possible for the
first time - git cannot forget, a table can.

THE SHAPE, and the reasoning is recorded because reshaping it later
should be cheap. Keith delegated this call on 2026-09-27 ("take the
mindset of a senior engineer who cares about long-term stability... I can
come back and reshape it if I need to"), so it is decided rather than
surveyed.

  `qa.run`           one row per QA run; everything keys to it. A run
                     table rather than repeating a run's facts on every
                     result row, because that is the one place a run's
                     identity could disagree with itself. It is also
                     where completeness lives - see below.

  `qa.check_result`  the resolved verdicts, as REAL COLUMNS for what
                     every tool shares plus a JSONB `extra` for what one
                     tool has. Columns are what make the history query
                     cheap; the sidecar is what stops a fifth tool
                     (REQ-QAC-096's file checks) needing a migration to
                     record one field nothing else has.

  `qa.tool_output`   each tool's own unmodified payload, in a SEPARATE
                     table. These are the bulk and almost nothing reads
                     them - a real dbt run_results.json is large - so
                     keeping them beside the verdicts would make every
                     verdict query risk dragging megabytes it does not
                     want. One join gets it on the rare day somebody is
                     debugging a tool. It is also what makes retention
                     practical: the bulk can be dropped without touching
                     a single verdict.

  `qa.tables_read`   which physical table each logical name resolved to,
                     per run. ROWS rather than a document, and the
                     contrast with dataset_stats below is the whole
                     reasoning: this is a uniform triple answering "which
                     version of this table did that run read", which is
                     exactly the audit question worth being queryable
                     across years.

  `qa.dataset_stats` the dashboard's presentation payload, as a JSONB
                     document. The ONE place this deliberately does not
                     normalise: its shape is the dashboard's, it changes
                     whenever a panel changes, and nothing else reads it,
                     so normalising would buy a migration per chart and
                     no query anybody runs.

A RUN IS NOT OBSERVABLE UNTIL IT SAYS IT IS FINISHED (criterion 13).
`qa.run.completed_at` is NULL while a run is in flight and every read in
this module joins through it, so a half-written run is not a run with
fewer results - it is no run at all. This is a structure rather than a
convention on purpose: "every reader remembers to filter" is the same as
no filter at all on the day one of them forgets, and a partial run
reading as a finished one is the exact false-green shape this project
keeps finding. The `qa.*_visible` views carry the same rule for anything
reading over a grant rather than through this module, which is how the
dashboard build gets it for free (criteria 7 and 23).

RESULTS ARE KEYED BY (run, tool, scope, supply_state), and that tuple is
inherited rather than invented - it is what the retired tree keyed a FILE
by, plus the one dimension criterion 24 adds. Writing replaces exactly
that tuple, so re-running one tool is idempotent and does not disturb
another tool's verdicts from the same run. An earlier draft of this
module replaced by (run, scope) alone, which would have had Soda silently
delete dbt's results; `tests/test_qa_store.py` holds that case.

`metric_value` is `double precision` rather than `numeric` on purpose. It
is a measurement for display and comparison, never money - and numeric
would hand psycopg a Decimal, which is exactly the bug this engine switch
already produced once, where json.dumps refused one on the way out.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from qa_tools.common import supply_db

#: The one reserved metadata schema. Refused as an agency, collection or
#: dataset id by the same gate that refuses a leading underscore, so a
#: real dataset can never collide with it.
SCHEMA = "qa"

#: A result's scope. `DATASET` is a dataset's own verdict; `CROSS_TABLE`
#: is REQ-QAC-037's record that spans datasets and belongs to none of
#: them. The spellings match the retired tree's own directory names so a
#: reader moving between the two is not learning a second vocabulary.
DATASET_SCOPE = "dataset"
CROSS_TABLE_SCOPE = "_cross-table"

#: Whether a result describes an agreed supply or a dataset still being
#: developed against (criterion 24, decision 1). The second is excluded
#: from every read that a viewer would take as real quality history -
#: structurally, by being the default filter rather than by each caller
#: remembering. It is NOT discarded: developing a check is real work and
#: the person doing it has to be able to see the verdicts.
AGREED = "agreed"
IN_DEVELOPMENT = "in-development"


class UnattributedRun(Exception):
    """A run tried to finish without saying who ran it (criterion 6)."""

#: Every column of `qa.check_result` that comes straight from a verified
#: record, in order. Anything a record carries that is NOT here lands in
#: `extra` - which is the behaviour that makes a new tool's own field
#: survive without a migration, and the reason this is an explicit list
#: rather than a set difference computed at the call site.
_RESULT_COLUMNS = (
    "dataset_id",
    "check_id", "check_name", "column_name", "dimension", "label",
    "status", "metric_value", "unit", "warn_threshold", "fail_threshold",
    "row_count_total", "row_count_invalid", "on_fail_action", "engine",
    "reference_run_id",
)

#: Taken from the INVOCATION rather than from the record, because that
#: is where they are actually known. The retired tree encoded agency,
#: collection and tool in the PATH and only `dataset_id` in the record,
#: which is the same split - a record carrying its own agency was never
#: how this worked, and trusting one would let a record file itself
#: under an agency the caller was not writing for. `scope` and
#: `supply_state` are here too because they key the write.
_KEY_COLUMNS = ("agency_id", "collection_id", "tool", "scope", "supply_state")

#: Bumped whenever the DDL below changes shape. `ensure_schema` reads
#: it and does nothing when it already matches, which is what keeps
#: migration DDL off the hot write path - see that function.
SCHEMA_VERSION = 6

DDL = f"""
CREATE SCHEMA IF NOT EXISTS "{SCHEMA}";

CREATE TABLE IF NOT EXISTS "{SCHEMA}".schema_version (
    only_row boolean PRIMARY KEY DEFAULT true CHECK (only_row),
    version  integer NOT NULL
);

CREATE TABLE IF NOT EXISTS "{SCHEMA}".run (
    run_key        text PRIMARY KEY,
    agency_id      text NOT NULL,
    collection_id  text NOT NULL,
    -- BOTH, for the reason `qa.delivery` keeps two: a timestamptz
    -- stores an INSTANT, not an offset, so reading it back gives the
    -- same moment on the server's clock rather than the one the run was
    -- recorded on. That offset is a fact - REQ-PIPE-048 is about which
    -- clock the asset is on - and it reaches the dashboard's display and
    -- the changelog. Caught by a test asserting the exact string it
    -- wrote and getting +00:00 back for +08:00.
    run_timestamp  text NOT NULL,
    run_instant    timestamptz NOT NULL,
    -- NULLABLE AT INSERT, REQUIRED AT COMPLETION. A run is registered by
    -- whoever gets there first - the orchestrator, which knows who is
    -- running it, or a bare single-tool invocation, which does not. What
    -- criterion 6 actually requires is that a FINISHED run says who ran
    -- it, so `complete_run` is where that is enforced. The alternative
    -- was a placeholder identity at insert, which CLAUDE.md's own rule
    -- on get_run_by() rules out: never fall back to one.
    run_by         text,
    environment    text,
    tool_versions  jsonb NOT NULL DEFAULT '{{}}',
    created_at     timestamptz NOT NULL DEFAULT now(),
    -- NULL while the run is in flight. Criterion 13 lives here.
    completed_at   timestamptz
);

-- Self-healing for a database created before run_by became nullable.
-- Harmless where it already is; DROP NOT NULL does not error on a
-- column that has none.
ALTER TABLE "{SCHEMA}".run ALTER COLUMN run_by DROP NOT NULL;
ALTER TABLE "{SCHEMA}".run ADD COLUMN IF NOT EXISTS run_instant timestamptz;
ALTER TABLE "{SCHEMA}".run ALTER COLUMN environment DROP NOT NULL;

CREATE INDEX IF NOT EXISTS run_completed
    ON "{SCHEMA}".run (completed_at) WHERE completed_at IS NOT NULL;

--   receipt order across runs, on the instant rather than the text
CREATE INDEX IF NOT EXISTS run_when ON "{SCHEMA}".run (run_instant);

CREATE TABLE IF NOT EXISTS "{SCHEMA}".check_result (
    id                bigserial PRIMARY KEY,
    run_key           text NOT NULL REFERENCES "{SCHEMA}".run ON DELETE CASCADE,
    agency_id         text NOT NULL,
    collection_id     text NOT NULL,
    dataset_id        text,
    scope             text NOT NULL DEFAULT '{DATASET_SCOPE}',
    supply_state      text NOT NULL DEFAULT '{AGREED}',
    tool              text NOT NULL,
    -- The IDENTITY is required; the label is not. REQ-QAC-039 made
    -- check_id the spine every history question keys on, so a verdict
    -- with no check_id is a verdict about nothing - refusing it is the
    -- loud failure criterion 12 asks for. `check_name` is a display
    -- string and a tool is entitled not to supply one.
    check_id          text NOT NULL,
    check_name        text,
    column_name       text,
    dimension         text,
    label             text,
    status            text NOT NULL,
    metric_value      double precision,
    unit              text,
    warn_threshold    double precision,
    fail_threshold    double precision,
    row_count_total   bigint,
    row_count_invalid bigint,
    on_fail_action    text,
    engine            text,
    reference_run_id  text,
    extra             jsonb NOT NULL DEFAULT '{{}}'
);

-- Self-healing, same as the run columns above: a database created
-- before check_name became a display string keeps its NOT NULL
-- otherwise.
ALTER TABLE "{SCHEMA}".check_result ALTER COLUMN check_name DROP NOT NULL;

-- Each index earns its place from a query that exists rather than from a
-- guess about one that might.
--   the check-history question this whole change is for
CREATE INDEX IF NOT EXISTS check_result_check_history
    ON "{SCHEMA}".check_result (check_id, run_key);
--   one dataset's results for one run, which is every dashboard page
CREATE INDEX IF NOT EXISTS check_result_dataset_run
    ON "{SCHEMA}".check_result (dataset_id, run_key);
--   the write key, which every record_results() call deletes by
CREATE INDEX IF NOT EXISTS check_result_write_key
    ON "{SCHEMA}".check_result (run_key, tool, scope, supply_state);
--   PARTIAL, because the interesting query is always the failures and
--   they are the minority - so the index stays small as history grows
CREATE INDEX IF NOT EXISTS check_result_not_passing
    ON "{SCHEMA}".check_result (dataset_id, check_id)
    WHERE status <> 'pass';

CREATE TABLE IF NOT EXISTS "{SCHEMA}".tool_output (
    run_key    text NOT NULL REFERENCES "{SCHEMA}".run ON DELETE CASCADE,
    tool       text NOT NULL,
    dataset_id text NOT NULL DEFAULT '',
    raw_output jsonb NOT NULL,
    PRIMARY KEY (run_key, tool, dataset_id)
);

CREATE TABLE IF NOT EXISTS "{SCHEMA}".tables_read (
    run_key        text NOT NULL REFERENCES "{SCHEMA}".run ON DELETE CASCADE,
    logical_table  text NOT NULL,
    physical_table text NOT NULL,
    PRIMARY KEY (run_key, logical_table)
);

--   "which runs read this table, in order" - the audit question
CREATE INDEX IF NOT EXISTS tables_read_logical
    ON "{SCHEMA}".tables_read (logical_table);

-- ONE RECORD PER LOAD ATTEMPT, append-only (REQ-PIPE-089 criterion 14,
-- carrying REQ-PIPE-060's criteria 13-20 across unchanged). It is not a
-- QA verdict and sits in its own table for that reason: a verdict says
-- what a check found, this says whether the data is readable at all.
CREATE TABLE IF NOT EXISTS "{SCHEMA}".load_outcome (
    -- LATEST WINS BY id, NOT BY TIMESTAMP. The file tree it replaces
    -- sorted on the recorded_at string, which works only while every
    -- writer uses one UTC offset - a second deployment in a different
    -- one would silently reorder history. A serial on an append-only
    -- table is insertion order, which is what "latest" actually means.
    id          bigserial PRIMARY KEY,
    delivery    text NOT NULL,
    dataset_id  text NOT NULL,
    physical    text NOT NULL,
    outcome     text NOT NULL,
    -- Kept as the exact text the writer recorded rather than parsed to
    -- timestamptz: it is read back and compared, and reformatting it
    -- through the server's session timezone would change the value
    -- without changing the instant. Ordering does not depend on it.
    recorded_at text NOT NULL,
    reason      text,
    row_count   bigint,
    -- NULL for a real load; the trial's own run id for a trial's
    -- (REQ-PIPE-103 criterion 2). A trial has to WRITE load records -
    -- they are the gate deciding which staged tables its views may
    -- resolve, so skipping them would have a trial run under a weaker
    -- rule than the real thing - and it has to leave none behind. A
    -- column does both, and does the second inside the same
    -- transaction that drops the trial's schemas, which the temporary
    -- directory it replaces could not.
    trial_run_id text
);

-- BRINGING AN OLDER DATABASE FORWARD. Bumping SCHEMA_VERSION makes
-- ensure_schema re-run this script, and that is necessary but NOT
-- sufficient: `CREATE TABLE IF NOT EXISTS` does nothing at all to a
-- table that already exists, so a column added to the definition above
-- never reaches a database created before it. Found by a real
-- database refusing the index below on a column it had never heard of.
-- Every column added from here needs its own ADD COLUMN IF NOT EXISTS.
ALTER TABLE "{SCHEMA}".load_outcome ADD COLUMN IF NOT EXISTS trial_run_id text;

--   a trial's own rows, for the delete that ends it
CREATE INDEX IF NOT EXISTS load_outcome_trial
    ON "{SCHEMA}".load_outcome (trial_run_id) WHERE trial_run_id IS NOT NULL;

--   the question every view resolution asks: is this table readable
CREATE INDEX IF NOT EXISTS load_outcome_latest
    ON "{SCHEMA}".load_outcome (physical, id DESC);
--   "has this delivery been processed", bounded by one delivery
CREATE INDEX IF NOT EXISTS load_outcome_delivery
    ON "{SCHEMA}".load_outcome (delivery);

CREATE TABLE IF NOT EXISTS "{SCHEMA}".dataset_stats (
    run_key    text NOT NULL REFERENCES "{SCHEMA}".run ON DELETE CASCADE,
    dataset_id text NOT NULL,
    stats      jsonb NOT NULL,
    PRIMARY KEY (run_key, dataset_id)
);

-- WHAT ARRIVED (REQ-PIPE-089 criterion 16), carrying REQ-PIPE-069's
-- write-once record across unchanged. THE ONE COPY: there is no
-- committed delivery_log/ beside this, because two records of the same
-- arrival are two records that can drift.
CREATE TABLE IF NOT EXISTS "{SCHEMA}".delivery (
    name        text PRIMARY KEY,
    -- BOTH, and each has a job. `received_at` is the exact text the
    -- recognition recorded, offset and all - REQ-PIPE-069 criterion 5
    -- protects that offset, because it says which clock the receiving
    -- side was on, and timestamptz stores an instant rather than an
    -- offset. `received_instant` is that instant, and is what ordering
    -- uses: sorting the text is only correct while every writer shares
    -- one offset.
    received_at      text NOT NULL,
    received_instant timestamptz NOT NULL,
    collections jsonb NOT NULL DEFAULT '[]',
    -- Derivable from the files below - two carrying one dataset_id -
    -- and stated anyway, for the reason REQ-PIPE-059 criterion 4 gave:
    -- the question a person opens this with is "what was held and what
    -- could it not choose between", and making them compute it is how
    -- a queue stops being drained.
    held        jsonb NOT NULL DEFAULT '[]',
    -- Recorded, never read. A receipt lookalike or a supplier's own
    -- manifest is excluded from the files on purpose, so this is the
    -- only place their presence survives.
    anomalies   jsonb NOT NULL DEFAULT '[]',
    recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS delivery_receipt_order
    ON "{SCHEMA}".delivery (received_instant);

CREATE TABLE IF NOT EXISTS "{SCHEMA}".delivery_file (
    delivery     text NOT NULL REFERENCES "{SCHEMA}".delivery ON DELETE CASCADE,
    filename     text NOT NULL,
    -- NULL where nothing claimed it, or where two datasets both did -
    -- a contested file is attributed to NEITHER, and `contested_by`
    -- says which two, because that is the difference between a record
    -- somebody can act on and one that just says "no".
    dataset_id   text,
    contested_by jsonb,
    PRIMARY KEY (delivery, filename)
);

--   "when did this dataset last arrive", across all deliveries. Real
--   columns rather than a JSONB document for the same reason
--   tables_read got them: this is the cross-record question worth
--   being able to ask at thirty datasets over years.
CREATE INDEX IF NOT EXISTS delivery_file_dataset
    ON "{SCHEMA}".delivery_file (dataset_id);

-- WHERE EACH SUPPLY WAS FILED (REQ-PIPE-104, carrying REQ-PIPE-062's
-- record across). A row rather than `filings/<dataset>/<supply>.json`,
-- which is what it was until this requirement - code with recording
-- switched off, so there was nothing to migrate and only a destination
-- to build.
--
-- WRITE-ONCE, AND THAT IS NOT THE SAME AS IMMUTABLE. The primary key
-- makes `record()` a no-op for a supply already filed, which is
-- criterion 2: a filing must never be re-derived against a schedule that
-- has since moved on, because the slot state it was decided against has
-- gone. A PERSON re-filing it is a different act and does update the row
-- - REQ-PIPE-067, and the verdict follows the filing. So no append-only
-- trigger here, unlike `qa.decision`: the two tables are protecting
-- different things.
--
-- `branch` IS STORED RATHER THAN RECOMPUTED, which looks redundant and
-- is the point: "why is this supply here" has to be answerable a year
-- later without re-running anything, and recomputing it then gives a
-- different answer. It is evidence about a moment, not a derived view.
CREATE TABLE IF NOT EXISTS "{SCHEMA}".filing (
    dataset_id  text NOT NULL,
    supply_id   text NOT NULL,
    -- NULLABLE: a supply the rule could find no slot for is HELD, and
    -- recording it with no slot is how it reaches the queue a person
    -- drains. A held supply with no row at all would be a supply nobody
    -- knows about.
    slot        text,
    branch      text NOT NULL,
    -- THE WHOLE Assignment RECORD, as a document. Normalising it would
    -- buy a migration for every field REQ-PIPE-064/065 add to an
    -- explanation and no query anybody runs - the same call
    -- `dataset_stats` made, and for the same reason. The three columns
    -- above are lifted out because they ARE queried: which slot, and why.
    record      jsonb NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_id, supply_id)
);

--   one dataset's filings, at a cost that does not grow with any other
--   dataset's history - the per-dataset shape REQ-PIPE-034 established
--   for arrivals, which the retired directory layout gave for free.
CREATE INDEX IF NOT EXISTS filing_dataset
    ON "{SCHEMA}".filing (dataset_id, recorded_at);

--   "what is filed against this slot", which is what a held or
--   contested supply is judged against.
CREATE INDEX IF NOT EXISTS filing_slot
    ON "{SCHEMA}".filing (dataset_id, slot) WHERE slot IS NOT NULL;

-- WHO DECIDED WHAT (REQ-PIPE-091, carrying REQ-PIPE-074's content
-- across). THE SINGLE SYSTEM OF RECORD for every filing decision -
-- there is no committed decision log beside it, which is REQ-PIPE-074
-- criteria 11 and 14 amended rather than met (Keith, 2026-09-27).
--
-- IT LIVES IN THIS SCHEMA, AND THAT IS THE WHOLE POINT rather than
-- tidiness: a decision and its effect on the warehouse have to land in
-- ONE transaction, and a transaction cannot span two databases. The
-- earlier design had the log as committed files and the effect in the
-- warehouse, which no mechanism can make atomic - so the record could
-- say a supply was promoted while the promotion had failed, or the
-- reverse, and nothing would say which happened.
--
-- IT HANGS OFF NOTHING. Every other table here cascades from `qa.run`,
-- and this one deliberately does not: a decision is not part of a QA
-- run, it is a person acting on what a run found, and `DELETE FROM run`
-- must never take a decision with it. It is also why regenerating QA
-- history leaves the log alone - the results can be recomputed, the
-- decisions cannot.
CREATE TABLE IF NOT EXISTS "{SCHEMA}".decision (
    id             bigserial PRIMARY KEY,
    agency_id      text NOT NULL,
    collection_id  text NOT NULL,
    dataset_id     text NOT NULL,
    action         text NOT NULL
        CHECK (action IN ('promote', 'reject', 'demote', 'refile')),
    -- The supply acted on, by the identity the rest of the system uses
    -- for one: a physical staged table name. Not a run id - a run is a
    -- check over a supply, and the same supply can be checked twice.
    supply         text NOT NULL CHECK (supply <> ''),
    -- A SLOT PAIR, so that a RE-FILE IS ONE ENTRY (REQ-PIPE-074
    -- criterion 9) rather than a demotion followed by a promotion.
    -- Expressed as two rows it would be two decisions with two reasons
    -- and an instant between them where the period had nothing at all,
    -- and a reader a year later could not tell that pair from somebody
    -- genuinely changing their mind twice.
    from_slot      text,
    to_slot        text,
    CHECK (from_slot IS NOT NULL OR to_slot IS NOT NULL),
    CHECK (action <> 'refile' OR (from_slot IS NOT NULL AND to_slot IS NOT NULL)),
    -- NO DEFAULT, NO PLACEHOLDER, NO 'unknown' (criterion 6, and
    -- REQ-PIPE-074 criterion 5). The empty-string check is the half
    -- that NOT NULL misses, and '' is exactly what a CLI passes when
    -- somebody hits return at a prompt.
    actor          text NOT NULL CHECK (actor <> ''),
    -- A PERSON OR A RULE (REQ-PIPE-074 criterion 4). "Promoted by
    -- auto-promotion" and "promoted by Keith" are different facts, and
    -- an audit that cannot separate them cannot answer the only
    -- question it exists for.
    actor_kind     text NOT NULL CHECK (actor_kind IN ('person', 'rule')),
    -- NULLABLE, because a routine promotion legitimately has none
    -- (REQ-PIPE-074 criterion 7) while a rejection, a red promotion and
    -- a supersession all require one (criterion 6). Which of those
    -- applies depends on the log as it stands, so it is judged in
    -- decision_log.py inside the transaction rather than by a column
    -- constraint that cannot see the other rows.
    reason         text,
    -- TWO INSTANTS, and they are different facts. `effective_at` is when
    -- the decision took effect on the warehouse; `recorded_at` is when
    -- this row was written. They are equal for anything this system
    -- does itself and are not for a decision taken earlier and recorded
    -- after the fact, which is the case an audit asks about.
    effective_at   timestamptz NOT NULL,
    recorded_at    timestamptz NOT NULL DEFAULT now()
);

--   one dataset's decisions, in the order they took effect, at a cost
--   that does not grow with any other dataset's history (criterion 11).
CREATE INDEX IF NOT EXISTS decision_dataset_order
    ON "{SCHEMA}".decision (dataset_id, effective_at, id);

--   "what is promoted into this slot", which is the judgement every
--   decision is made against.
CREATE INDEX IF NOT EXISTS decision_slot
    ON "{SCHEMA}".decision (dataset_id, to_slot, effective_at)
    WHERE to_slot IS NOT NULL;

-- APPEND-ONLY, ENFORCED BY THE DATABASE (criterion 5).
--
-- A TRIGGER RATHER THAN ONLY A GRANT, and both are here rather than
-- either. A grant is bypassed by a superuser and by the table's owner,
-- which in this project is the role every developer connects as - so
-- grants alone would leave the guarantee true of the dashboard's reader
-- and false of everybody who could actually do the damage. A trigger
-- applies to every role including the owner.
--
-- IT RAISES rather than silently doing nothing. `DO INSTEAD NOTHING`
-- would make an UPDATE report success having changed nothing, which is
-- worse than either outcome: the caller believes it worked.
CREATE OR REPLACE FUNCTION "{SCHEMA}".decision_is_append_only()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'qa.decision is append-only: a % is not permitted. Express a reversal '
        'as a new entry.', lower(TG_OP);
END;
$$;

-- TWO TRIGGERS, because PostgreSQL refuses TRUNCATE alongside any other
-- event in one trigger - and TRUNCATE is the one that matters most here,
-- being the fastest way to lose the whole log by accident. This schema's
-- own fixtures truncate `qa.run` routinely.
DROP TRIGGER IF EXISTS decision_append_only ON "{SCHEMA}".decision;
CREATE TRIGGER decision_append_only
    BEFORE UPDATE OR DELETE ON "{SCHEMA}".decision
    FOR EACH STATEMENT EXECUTE FUNCTION "{SCHEMA}".decision_is_append_only();

DROP TRIGGER IF EXISTS decision_no_truncate ON "{SCHEMA}".decision;
CREATE TRIGGER decision_no_truncate
    BEFORE TRUNCATE ON "{SCHEMA}".decision
    FOR EACH STATEMENT EXECUTE FUNCTION "{SCHEMA}".decision_is_append_only();

-- THE VISIBLE VIEWS carry criterion 13 for readers that come over a
-- GRANT rather than through this module - which is how the dashboard
-- build gets the rule for free (criteria 7 and 23). The publisher role
-- is granted these and never the base tables, so "only finished runs"
-- is something the database enforces rather than something a build
-- remembers.
CREATE OR REPLACE VIEW "{SCHEMA}".run_visible AS
    SELECT * FROM "{SCHEMA}".run WHERE completed_at IS NOT NULL;

CREATE OR REPLACE VIEW "{SCHEMA}".check_result_visible AS
    SELECT r.* FROM "{SCHEMA}".check_result r
    JOIN "{SCHEMA}".run ON run.run_key = r.run_key
    WHERE run.completed_at IS NOT NULL;

CREATE OR REPLACE VIEW "{SCHEMA}".tool_output_visible AS
    SELECT t.* FROM "{SCHEMA}".tool_output t
    JOIN "{SCHEMA}".run ON run.run_key = t.run_key
    WHERE run.completed_at IS NOT NULL;

CREATE OR REPLACE VIEW "{SCHEMA}".tables_read_visible AS
    SELECT t.* FROM "{SCHEMA}".tables_read t
    JOIN "{SCHEMA}".run ON run.run_key = t.run_key
    WHERE run.completed_at IS NOT NULL;

CREATE OR REPLACE VIEW "{SCHEMA}".dataset_stats_visible AS
    SELECT d.* FROM "{SCHEMA}".dataset_stats d
    JOIN "{SCHEMA}".run ON run.run_key = d.run_key
    WHERE run.completed_at IS NOT NULL;
"""


#: An arbitrary but FIXED key for the advisory lock below. Any two
#: sessions agreeing on the same number serialise against each other;
#: the value itself means nothing beyond "this project's QA schema".
_DDL_LOCK = 8_9_0_0_8_9

def ensure_schema(conn: supply_db.SupplyConnection) -> None:
    """Create the metadata schema if it is not there.

    Safe to call from every writer rather than from one privileged setup
    step - which is deliberate: a pipeline that only works after
    somebody remembered to run a migration is a pipeline that fails on a
    new environment.

    THE ADVISORY LOCK IS NOT BELT AND BRACES. `CREATE SCHEMA IF NOT
    EXISTS` is not atomic against a concurrent `CREATE SCHEMA` -
    PostgreSQL checks, then creates, and two sessions can both pass the
    check. The first real `mothman pipeline bootstrap` against this
    schema died on exactly that: its two collections run in parallel,
    both reached here, and one lost with `duplicate key value violates
    unique constraint "pg_namespace_nspname_index"`. Child Protection
    recorded nothing that run.

    `IF NOT EXISTS` reads as the careful option, which is what makes it
    worth naming: every CREATE in the DDL above carries the same hazard,
    so the lock covers the whole script rather than that one statement.
    A session-level lock with an explicit release, because these
    connections are autocommit and so have no transaction for
    `pg_advisory_xact_lock` to hang off.

    THE VERSION CHECK IS WHAT KEEPS THE DDL OFF THE HOT PATH, and it is
    there because the lock alone was not enough. Running the whole
    script on every write meant `ALTER TABLE ... DROP NOT NULL` and
    `CREATE OR REPLACE VIEW` - both AccessExclusiveLock - contending
    with parallel workers holding RowShareLock on `qa.run` for their
    foreign-key checks. The second real bootstrap deadlocked and
    PostgreSQL killed a dbt run. Migration DDL belongs where the shape
    changes, not where a result is written.
    """
    if _is_current(conn):
        return
    conn.execute("SELECT pg_advisory_lock(?)", [_DDL_LOCK])
    try:
        # Re-checked INSIDE the lock. Whoever was ahead in the queue has
        # finished by now, so without this every waiting session runs
        # the whole DDL again in turn - which is the thing being avoided.
        if _is_current(conn):
            return
        conn.raw.execute(DDL)
        conn.execute(
            f'INSERT INTO "{SCHEMA}".schema_version (version) VALUES (?) '
            "ON CONFLICT (only_row) DO UPDATE SET version = EXCLUDED.version",
            [SCHEMA_VERSION])
    finally:
        conn.execute("SELECT pg_advisory_unlock(?)", [_DDL_LOCK])


def _is_current(conn: supply_db.SupplyConnection) -> bool:
    """Whether the schema is already at SCHEMA_VERSION.

    One cheap SELECT against a one-row table, and deliberately not a
    per-process cache: the test suite drops and rebuilds this schema,
    and a cache would happily report a schema that is no longer there.
    """
    if not conn.execute(
            f"SELECT to_regclass('{SCHEMA}.schema_version')").fetchall()[0][0]:
        return False
    rows = conn.execute(f'SELECT version FROM "{SCHEMA}".schema_version').fetchall()
    return bool(rows) and rows[0][0] == SCHEMA_VERSION


#: Schemas the publisher must never reach. Named rather than derived,
#: because the point is that a new one has to be added DELIBERATELY - a
#: derivation would quietly admit whatever came along next, which is
#: the failure mode a least-privilege grant exists to prevent.
SUPPLY_SCHEMA_PREFIXES = ("staging", "rejected", "promoted", "period_", "sample",
                          "qa_run_", "dbt_", "trial_")


def ensure_publisher_role(conn: supply_db.SupplyConnection, role: str,
                          password: str | None = None) -> None:
    """Create or update the role the dashboard build connects as
    (criteria 7 and 23).

    READ ON THE METADATA SCHEMA, AND NOTHING ELSE. Not "everything
    except supply data" - the difference matters, because a grant
    written as an exclusion has to be revisited every time a schema is
    added, and the one nobody revisits is the one that leaks. This
    grants USAGE on `qa` alone; every other schema is unreachable
    because nothing was ever granted on it.

    DEFAULT PRIVILEGES ARE PART OF THE GRANT, not a refinement. Without
    them the next table added to this schema arrives unreadable, and
    the person who hits that at 6pm fixes it with a broader grant than
    anybody intended.

    WHY A ROLE RATHER THAN A SEPARATE DATABASE (Keith, 2026-09-26): the
    claim that a second database means the publisher "literally cannot"
    read supply data was overstated - it is a grant either way. What
    separation buys is least privilege per component, and a role buys
    the same; against a second database is REQ-PIPE-075 criterion 9's
    ordering rule, which collapses into one transaction only while the
    log and the tables share a database.

    NEEDS A SUPERUSER (or CREATEROLE) connection, and says so rather
    than half-succeeding: a role created without its grants is worse
    than no role, because it authenticates and then fails at read time
    somewhere far away.
    """
    quoted = f'"{supply_db._ident(role, "role name")}"'
    exists = conn.execute(
        "SELECT 1 FROM pg_roles WHERE rolname = ?", [role]).fetchall()
    if not exists:
        conn.execute(f"CREATE ROLE {quoted} LOGIN")
    if password is not None:
        conn.execute(f"ALTER ROLE {quoted} WITH PASSWORD '{password}'")

    conn.execute(f'GRANT USAGE ON SCHEMA "{SCHEMA}" TO {quoted}')
    conn.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{SCHEMA}" TO {quoted}')
    conn.execute(
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{SCHEMA}" GRANT SELECT ON TABLES TO {quoted}')

    # WRITE IS REVOKED EXPLICITLY, not merely never granted
    # (REQ-PIPE-091 criteria 5 and 10). Never-granted is the true
    # statement today and is not the one worth relying on: the grant
    # above is `SELECT ON ALL TABLES`, and the next person who needs this
    # role to write one thing will widen that line rather than add a
    # second. A REVOKE standing beside it says the absence was decided.
    #
    # It also makes criterion 10 real rather than incidental - a reader
    # with no write access can read the WHOLE decision history, including
    # the entries append-only would stop even a writer from changing.
    conn.execute(
        f'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA "{SCHEMA}" '
        f"FROM {quoted}")
    conn.execute(
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{SCHEMA}" '
        f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLES FROM {quoted}")

    # THE PUBLIC SCHEMA, and this used to be a NO-OP that read like a
    # safeguard - found 2026-09-28 while asserting criterion 4 of
    # REQ-PIPE-104. It was `REVOKE ALL ON SCHEMA public FROM <the role>`,
    # and PostgreSQL grants `public` to the PUBLIC pseudo-role rather than
    # to each role individually, so revoking from one role removes
    # nothing: `has_schema_privilege(role, 'public', 'USAGE')` still came
    # back true. The comment claimed the schema had been removed from this
    # role's reach and it had not.
    #
    # REVOKED FROM PUBLIC, which is the grant that actually exists. It is
    # database-wide by nature - that is what PUBLIC means - and safe here:
    # every other connection this project opens is the owning superuser,
    # and a superuser bypasses grants entirely. On PostgreSQL 15 and later
    # `public` carries USAGE but no CREATE for PUBLIC, so what this
    # removes is the ability to LOOK; nothing in this project puts a table
    # there, and this is what stops one appearing there later and being
    # readable by a role nobody granted it to.
    #
    # The per-role revoke stays beside it: harmless, and it covers a
    # direct grant somebody might add.
    conn.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    conn.execute(f"REVOKE ALL ON SCHEMA public FROM {quoted}")


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def record_run(conn: supply_db.SupplyConnection, *, run_key: str, agency_id: str,
               collection_id: str, run_timestamp: str, run_by: str | None = None,
               environment: str | None = None,
               tool_versions: Mapping[str, str] | None = None) -> None:
    """Register a run, or update it where it is re-run.

    ON CONFLICT rather than a prior existence check, because two workers
    in the same fan-out can legitimately reach this at the same moment -
    and a check-then-insert is a race with a nice-looking shape.

    IT DOES NOT TOUCH `completed_at`, so registering a run that already
    finished does not quietly un-finish it; `reopen_run` is the explicit
    way to do that and says so at the call site.

    IT ALSO DOES NOT REPLACE A KNOWN IDENTITY WITH AN UNKNOWN ONE. A
    tool's own write registers the run defensively and has no `run_by`;
    the orchestrator's does and is the one that knows. Plain EXCLUDED
    would make the last writer win, which here means the one with less
    information - so each field keeps what it had unless the caller
    actually supplies something.
    """
    conn.execute(
        f'INSERT INTO "{SCHEMA}".run '
        "(run_key, agency_id, collection_id, run_timestamp, run_instant, run_by, "
        "environment, tool_versions) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (run_key) DO UPDATE SET "
        "run_timestamp = EXCLUDED.run_timestamp, "
        "run_instant = EXCLUDED.run_instant, "
        f'run_by = COALESCE(EXCLUDED.run_by, "{SCHEMA}".run.run_by), '
        f'environment = COALESCE(EXCLUDED.environment, "{SCHEMA}".run.environment), '
        # A plain string, not an f-string: the empty-object literal is
        # two real braces in the SQL, and doubling them here would send
        # PostgreSQL '{{}}' - a one-element array containing an empty
        # object, which is not the same thing and would never match.
        "tool_versions = CASE WHEN EXCLUDED.tool_versions = '{}'::jsonb "
        f'THEN "{SCHEMA}".run.tool_versions ELSE EXCLUDED.tool_versions END',
        [run_key, agency_id, collection_id, run_timestamp, run_timestamp, run_by,
         environment, json.dumps(dict(tool_versions or {}))])


def complete_run(conn: supply_db.SupplyConnection, run_key: str) -> None:
    """Mark a run finished, which is what makes its results observable.

    The one place completeness flips, which is why the run is a table at
    all (decision 2). Without it, completeness has to be inferred by
    counting results against an expectation - and an expectation that
    can be wrong is how a partial run reads as a finished one.

    THIS IS WHERE CRITERION 6 IS ENFORCED - a finished run says who ran
    it and when, or it does not finish. Refusing here rather than at
    registration is what lets a bare single-tool invocation open a run
    without inventing an identity for it.
    """
    rows = conn.execute(
        f'UPDATE "{SCHEMA}".run SET completed_at = now() '
        "WHERE run_key = ? AND run_by IS NOT NULL AND environment IS NOT NULL "
        "RETURNING run_key", [run_key]).fetchall()
    if not rows:
        raise UnattributedRun(
            f"run {run_key!r} cannot be completed: it is not registered, or it has "
            "no run_by/environment recorded. A finished run has to say who ran it "
            "and where (REQ-PIPE-089 criterion 6).")


def reopen_run(conn: supply_db.SupplyConnection, run_key: str) -> None:
    """Put a finished run back in flight, for a re-run.

    Re-running is a real thing this pipeline does, so the marker must not
    latch - but it has to be deliberate, because the alternative is
    `record_run` silently un-finishing a run somebody is reading.
    """
    conn.execute(f'UPDATE "{SCHEMA}".run SET completed_at = NULL WHERE run_key = ?',
                 [run_key])


def record_results(conn: supply_db.SupplyConnection, run_key: str,
                   results: Sequence[Mapping[str, Any]], *, tool: str,
                   agency_id: str, collection_id: str,
                   scope: str = DATASET_SCOPE,
                   supply_state: str = AGREED) -> int:
    """Write one tool's resolved check results. Returns how many landed.

    REPLACES THIS (run, tool, scope, supply_state) rather than appending,
    so re-running one tool is idempotent - the same reasoning the retired
    writer had for overwriting a file rather than accumulating versions
    inside one, and the same key that file had.
    """
    conn.execute(
        f'DELETE FROM "{SCHEMA}".check_result '
        "WHERE run_key = ? AND tool = ? AND scope = ? AND supply_state = ?",
        [run_key, tool, scope, supply_state])
    columns = ("run_key", *_RESULT_COLUMNS, *_KEY_COLUMNS, "extra")
    placeholders = ", ".join(["?"] * len(columns))
    keys = (agency_id, collection_id, tool, scope, supply_state)
    # A record that names its own agency, collection or tool has those
    # DROPPED rather than carried into `extra`: they are the same fact
    # the invocation already stated, and keeping a second copy is how
    # the two come to disagree.
    ignored = set(_RESULT_COLUMNS) | set(_KEY_COLUMNS) | {"run_id", "run_timestamp"}
    rows = 0
    for record in results:
        values = [record.get(name) for name in _RESULT_COLUMNS]
        extra = {k: v for k, v in record.items() if k not in ignored}
        conn.execute(
            f'INSERT INTO "{SCHEMA}".check_result ({", ".join(columns)}) '
            f"VALUES ({placeholders})",
            [run_key, *values, *keys, json.dumps(extra, default=str)])
        rows += 1
    return rows


def record_tool_output(conn: supply_db.SupplyConnection, run_key: str, tool: str,
                       raw_output: Any, dataset_id: str | None = None) -> None:
    """Keep a tool's own unmodified payload."""
    conn.execute(
        f'INSERT INTO "{SCHEMA}".tool_output (run_key, tool, dataset_id, raw_output) '
        "VALUES (?, ?, ?, ?) ON CONFLICT (run_key, tool, dataset_id) "
        "DO UPDATE SET raw_output = EXCLUDED.raw_output",
        [run_key, tool, dataset_id or "", json.dumps(raw_output, default=str)])


def record_tables_read(conn: supply_db.SupplyConnection, run_key: str,
                       resolved: Mapping[str, str]) -> None:
    """Record which physical table each logical name resolved to."""
    for logical, physical in sorted(resolved.items()):
        conn.execute(
            f'INSERT INTO "{SCHEMA}".tables_read (run_key, logical_table, physical_table) '
            "VALUES (?, ?, ?) ON CONFLICT (run_key, logical_table) "
            "DO UPDATE SET physical_table = EXCLUDED.physical_table",
            [run_key, logical, physical])


def record_dataset_stats(conn: supply_db.SupplyConnection, run_key: str,
                         dataset_id: str, stats: Mapping[str, Any]) -> None:
    """Keep the dashboard's presentation payload for one dataset."""
    conn.execute(
        f'INSERT INTO "{SCHEMA}".dataset_stats (run_key, dataset_id, stats) '
        "VALUES (?, ?, ?) ON CONFLICT (run_key, dataset_id) "
        "DO UPDATE SET stats = EXCLUDED.stats",
        [run_key, dataset_id, json.dumps(stats, default=str)])


# ---------------------------------------------------------------------------
# Reading it back
#
# These are the queries the retired file-tree reader had to walk the tree
# to answer. Each one is here rather than assembled at a call site so the
# indexes above have a fixed set of shapes to serve - and so that
# criterion 13's join is in one place rather than in every caller.
# ---------------------------------------------------------------------------

def results_for_run(conn: supply_db.SupplyConnection, run_key: str,
                    dataset_id: str | None = None, *,
                    scope: str = DATASET_SCOPE,
                    supply_state: str | None = AGREED) -> list[dict]:
    """One run's verdicts. Only a finished run has any.

    `supply_state` defaults to AGREED rather than to everything, so a
    caller has to ASK for in-development verdicts to see them - criterion
    24 the way round that fails safe.
    """
    sql = (f'SELECT r.* FROM "{SCHEMA}".check_result_visible r '
           "WHERE r.run_key = ? AND r.scope = ?")
    params: list[Any] = [run_key, scope]
    if supply_state is not None:
        sql += " AND r.supply_state = ?"
        params.append(supply_state)
    if dataset_id is not None:
        sql += " AND r.dataset_id = ?"
        params.append(dataset_id)
    return _dicts(conn.execute(sql + " ORDER BY r.id", params))


def cross_table_results(conn: supply_db.SupplyConnection, run_key: str, *,
                        supply_state: str | None = AGREED) -> list[dict]:
    """The records that span datasets and belong to none of them."""
    return results_for_run(conn, run_key, scope=CROSS_TABLE_SCOPE,
                           supply_state=supply_state)


def history_for_check(conn: supply_db.SupplyConnection, check_id: str,
                      dataset_id: str | None = None, *,
                      supply_state: str | None = AGREED) -> list[dict]:
    """Every result this check has ever produced.

    The question the file tree could only answer by being walked in full,
    and the reason check_result_check_history exists.
    """
    sql = (f'SELECT r.*, run.run_timestamp FROM "{SCHEMA}".check_result_visible r '
           f'JOIN "{SCHEMA}".run_visible run USING (run_key) WHERE r.check_id = ?')
    params: list[Any] = [check_id]
    if supply_state is not None:
        sql += " AND r.supply_state = ?"
        params.append(supply_state)
    if dataset_id is not None:
        sql += " AND r.dataset_id = ?"
        params.append(dataset_id)
    return _dicts(conn.execute(sql + " ORDER BY run.run_instant, r.id", params))


def runs_for(conn: supply_db.SupplyConnection, agency_id: str,
             collection_id: str) -> list[dict]:
    return _dicts(conn.execute(
        f'SELECT * FROM "{SCHEMA}".run_visible WHERE agency_id = ? AND collection_id = ? '
        "ORDER BY run_instant, run_key", [agency_id, collection_id]))


def delete_history(conn: supply_db.SupplyConnection, agency_id: str,
                   collection_id: str) -> int:
    """Delete one collection's whole recorded QA history. Returns the
    number of runs removed.

    THE ONLY DESTRUCTIVE READER-FACING OPERATION IN THIS MODULE, and it
    exists for one caller: `mothman pipeline regenerate-history`
    (REQ-PIPE-038 criteria 4-7), whose whole job is to throw a
    collection's history away and write it again from the real tools.
    Keith's own call, 2026-09-21: the data is synthetic, so re-running is
    honest where reshaping in place would not be.

    ONE DELETE, NOT SEVEN. Everything hangs off `run` by a foreign key
    with ON DELETE CASCADE, so removing the runs removes their results,
    tool output, tables_read and dataset_stats with them - which is the
    point of having modelled it that way. A per-table sweep would be
    seven statements that can disagree about what a collection is.

    IT DELETES INCOMPLETE RUNS TOO, deliberately: this reads `run`
    rather than `run_visible`. A crashed run's wreckage is exactly what
    somebody regenerating wants gone, and leaving it would make the
    regenerated history carry a run nothing can read.
    """
    deleted = conn.execute(
        f'DELETE FROM "{SCHEMA}".run WHERE agency_id = ? AND collection_id = ?',
        [agency_id, collection_id]).rowcount
    return deleted or 0


def incomplete_runs(conn: supply_db.SupplyConnection) -> list[str]:
    """Runs that started and never said they finished.

    Invisible to a reader of RESULTS is not invisible full stop - an
    operator has to be able to find the wreckage of a crashed run, and
    this is the only thing that can see it.
    """
    return [row[0] for row in conn.execute(
        f'SELECT run_key FROM "{SCHEMA}".run WHERE completed_at IS NULL '
        "ORDER BY created_at").fetchall()]


def tables_read_for_run(conn: supply_db.SupplyConnection, run_key: str) -> dict[str, str]:
    """{logical table: the physical table this run actually read}."""
    return {logical: physical for logical, physical in conn.execute(
        f'SELECT logical_table, physical_table FROM "{SCHEMA}".tables_read_visible '
        "WHERE run_key = ? ORDER BY logical_table", [run_key]).fetchall()}


def table_history(conn: supply_db.SupplyConnection, logical_table: str) -> list[dict]:
    """Which version of one logical table each run read, oldest first."""
    return _dicts(conn.execute(
        f'SELECT t.*, run.run_timestamp FROM "{SCHEMA}".tables_read_visible t '
        f'JOIN "{SCHEMA}".run_visible run USING (run_key) WHERE t.logical_table = ? '
        "ORDER BY run.run_instant", [logical_table]))


def tool_output_for(conn: supply_db.SupplyConnection, run_key: str, tool: str,
                    dataset_id: str | None = None) -> Any:
    """One tool's own unmodified payload, on the rare day somebody wants it."""
    rows = conn.execute(
        f'SELECT raw_output FROM "{SCHEMA}".tool_output_visible '
        "WHERE run_key = ? AND tool = ? AND dataset_id = ?",
        [run_key, tool, dataset_id or ""]).fetchall()
    return rows[0][0] if rows else None


def dataset_stats_for(conn: supply_db.SupplyConnection, run_key: str,
                      dataset_id: str) -> dict | None:
    rows = conn.execute(
        f'SELECT stats FROM "{SCHEMA}".dataset_stats_visible '
        "WHERE run_key = ? AND dataset_id = ?",
        [run_key, dataset_id]).fetchall()
    return rows[0][0] if rows else None


def _dicts(cursor) -> list[dict]:
    """Rows as dicts, keyed by the column names the query actually
    returned - never by a hand-maintained list, which is how a new column
    gets silently dropped on the way out."""
    columns = [d.name for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
