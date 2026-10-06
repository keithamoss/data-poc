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
#: File checks' own scope (REQ-QAC-096 criterion 7): a statement about the
#: FILE as delivered, never about the dataset's data, so never in either
#: scope above - which is what keeps every data-check reader from seeing it
#: without each one having to remember to filter it out.
FILE_SCOPE = "_file"

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
SCHEMA_VERSION = 33

#: The version at which REQ-PIPE-144 RESHAPED qa.filing and qa.delivery
#: (a column removed, a column replaced by a foreign key). `CREATE TABLE
#: IF NOT EXISTS` leaves an existing table exactly as it was, so the DDL
#: below cannot bring an older database forward without half-applying
#: itself; a database recorded below this is refused and rebuilt from
#: empty instead (criterion 29 - regenerate, never migrate). Versions at
#: or above it are still brought forward additively.
RESHAPED_AT = 18


class SchemaVersionError(RuntimeError):
    """The qa schema in this database is from a version this checkout
    cannot safely apply its own definitions over (REQ-PIPE-144 criterion
    29, REQ-PIPE-107 criterion 13)."""

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
    completed_at   timestamptz,
    -- WHAT THIS RUN IS FOR (REQ-PIPE-140), stated rather than read off the
    -- run id. `arrival` is a supply's first run, made by its arrival;
    -- `full` a decision-triggered re-run of a supply's own checks and the
    -- cross-table checks reading it; `readers` only the cross-table checks
    -- reading `reads_table` in `period` (criterion 2). NULL supply for a
    -- trial's or a fixture's run, which belongs to no supply.
    dataset_id     text,
    supply_id      text,
    scope          text NOT NULL DEFAULT 'arrival'
                   CHECK (scope IN ('arrival', 'full', 'readers')),
    period         text,
    reads_table    text,
    -- THE CAUSE OF A RE-RUN (criterion 4): the decision, or the load
    -- record of a failed load that has since loaded (REQ-DASH-148). No
    -- foreign key on either: the decision log is never cascaded from a
    -- run, and load records are truncated by the test suite's cleanup.
    caused_by_decision bigint,
    caused_by_load     bigint,
    CHECK (scope = 'arrival'
           OR (caused_by_decision IS NULL) <> (caused_by_load IS NULL)),
    CHECK (scope <> 'readers' OR (reads_table IS NOT NULL AND period IS NOT NULL))
);

--   "this supply's runs, newest first" - criterion 5's read
CREATE INDEX IF NOT EXISTS run_supply
    ON "{SCHEMA}".run (dataset_id, supply_id, run_instant) WHERE supply_id IS NOT NULL;

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

-- A FILE CHECK'S RESULT NAMES THE LOAD ATTEMPT, DELIVERY AND FILE it was
-- about (REQ-QAC-096 criteria 7 and 8), schema 29. NULL for every other
-- tool's result. The load attempt is qa.load_outcome's id, with no foreign
-- key for the reason run.caused_by_load has none: load records are
-- truncated by the test suite's cleanup, and a result must not vanish with
-- them. Real columns rather than `extra`, because "which file was wrong"
-- is the question a reader of a several-file delivery asks first.
ALTER TABLE "{SCHEMA}".check_result ADD COLUMN IF NOT EXISTS load_attempt bigint;
ALTER TABLE "{SCHEMA}".check_result ADD COLUMN IF NOT EXISTS delivery text;
ALTER TABLE "{SCHEMA}".check_result ADD COLUMN IF NOT EXISTS filename text;

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
    -- THE SUPPLY A PERIOD TABLE HELD WHEN IT WAS READ (REQ-PIPE-129
    -- criterion 13): a period table carries its plain base name, so the
    -- name alone no longer says which supply it was. NULL for a staged
    -- table, whose stamped name says so itself.
    supply         text,
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
    -- WHICH CLOCK STAMPED IT (REQ-PIPE-105 criterion 4): our own storage's
    -- record of taking the object, or ours at the moment of receipt.
    -- Recorded rather than inferred, because anything judging whether a
    -- supply was late is judging that instant, and the two are different
    -- claims about how sure we are of it.
    --
    -- DEFAULTS TO 'our-clock', which is the weaker of the two, so a record
    -- written before this column existed does not come to assert that
    -- storage said something it never did.
    received_from    text NOT NULL DEFAULT 'our-clock',
    collections jsonb NOT NULL DEFAULT '[]',
    -- NO `contested` COLUMN (REQ-PIPE-144 criterion 25). Which datasets
    -- matched more than one file is derived from delivery_file by the
    -- delivery_contested view below - a second copy is a copy that can
    -- disagree.
    -- Recorded, never read. A receipt lookalike or a supplier's own
    -- manifest is excluded from the files on purpose, so this is the
    -- only place their presence survives.
    anomalies   jsonb NOT NULL DEFAULT '[]',
    recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS delivery_receipt_order
    ON "{SCHEMA}".delivery (received_instant);

-- WHO FILED IT (REQ-PIPE-147), version 19 - added, so ADD COLUMN rather
-- than a reshape. As DATA, never inferred from a `handfiled-` name or a
-- receipt clock (criterion 1): `automated`, or `person` with the route
-- (criterion 2, a closed set of four) and who (criterion 3, the same
-- identity qa.run.run_by carries).
ALTER TABLE "{SCHEMA}".delivery
    ADD COLUMN IF NOT EXISTS filed_by_kind text NOT NULL DEFAULT 'automated';
ALTER TABLE "{SCHEMA}".delivery ADD COLUMN IF NOT EXISTS filing_route text;
ALTER TABLE "{SCHEMA}".delivery ADD COLUMN IF NOT EXISTS filed_by text;
ALTER TABLE "{SCHEMA}".delivery DROP CONSTRAINT IF EXISTS delivery_filed_by_shape;
ALTER TABLE "{SCHEMA}".delivery ADD CONSTRAINT delivery_filed_by_shape CHECK (
    (filed_by_kind = 'automated' AND filing_route IS NULL AND filed_by IS NULL)
    OR (filed_by_kind = 'person'
        AND filing_route IN ('file', 'folder', 'table', 's3') AND filed_by IS NOT NULL));

CREATE TABLE IF NOT EXISTS "{SCHEMA}".delivery_file (
    delivery     text NOT NULL REFERENCES "{SCHEMA}".delivery ON DELETE CASCADE,
    filename     text NOT NULL,
    -- NULL where nothing claimed it, or where two datasets both did -
    -- a contested file is attributed to NEITHER, and `contested_by`
    -- says which two, because that is the difference between a record
    -- somebody can act on and one that just says "no".
    dataset_id   text,
    contested_by jsonb,
    -- THIS FILE'S OWN RECEIPT (REQ-PIPE-144 criterion 9) - one receipt
    -- per file since 2026-10-02 (REQ-GEN-044 criterion 12). The same
    -- text-plus-instant pair qa.delivery keeps, for the same reason: the
    -- text preserves the writer's offset (REQ-PIPE-069 criterion 5), the
    -- instant is what ordering uses. `receipt_sequence` is the
    -- receipt-order tiebreak (REQ-PIPE-061), without which two files
    -- received at one instant could not be put in the order arrivals
    -- were.
    received_at      text NOT NULL,
    received_instant timestamptz NOT NULL,
    received_from    text NOT NULL,
    receipt_sequence integer NOT NULL,
    PRIMARY KEY (delivery, filename)
);

-- A PERSON'S STATEMENT OF WHEN THIS FILE WAS ORIGINALLY RECEIVED
-- (REQ-PIPE-103 criteria 9-18), version 19. Beside the receipt, NEVER the
-- receipt: an ISO instant with its offset, or 'not-known'; NULL means
-- nobody was asked (criterion 18). Nothing orders, names, files, judges
-- or promotes on it (criterion 11) - it is a note, not a fact we hold.
ALTER TABLE "{SCHEMA}".delivery_file ADD COLUMN IF NOT EXISTS originally_received_stated text;
-- AND ITS INSTANT BESIDE IT (NFR 6, built 2026-10-05, Keith; schema 24):
-- the receipt's own text-plus-instant convention. NULL for 'not-known'
-- and where nobody was asked. Still a note - nothing decides on it.
ALTER TABLE "{SCHEMA}".delivery_file ADD COLUMN IF NOT EXISTS originally_received_stated_instant timestamptz;
-- WHERE THE FILE IS (REQ-PIPE-152, qa schema 33): `local:<delivery>/<file>`,
-- relative to the deliveries tree so a database restored on another machine
-- finds it under that machine's own, or `s3://<bucket>/<key>` for an object a
-- handler recorded without copying it. The processing pass builds every
-- arrival from these rows and fetches an S3 object when it stages it. NULL
-- only in a database recorded before the column, which a rebuild replaces.
ALTER TABLE "{SCHEMA}".delivery_file ADD COLUMN IF NOT EXISTS storage_uri text;

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
    -- THE SLOTS THE RULE CONSIDERED, in the order it considered them
    -- (REQ-PIPE-144 criterion 3; REQ-PIPE-062 criterion 9). Its own
    -- column rather than a key in a document, so it reads back without
    -- unpacking anything. There is NO `record` document any more
    -- (criterion 1): every field it held is a column here, equal to one
    -- (resupply_of is the slot), kept in qa.hold.reason (why a held
    -- supply's slots were unavailable), or retired (the ambiguity mark).
    considered  text[] NOT NULL DEFAULT '{{}}',
    -- THE DELIVERY IT CAME FROM (criterion 10), and the database refuses
    -- to delete a delivery a filing names: delivery records are history
    -- (criterion 19). The supply's RECEIPT is read through this link from
    -- the supply_receipt view below - there is no received_at column
    -- here, because the file's own receipt on qa.delivery_file is the one
    -- copy.
    delivery    text NOT NULL REFERENCES "{SCHEMA}".delivery (name),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    -- THE VERDICT THE RECEIPT EARNS AGAINST THIS SLOT (REQ-PIPE-080
    -- criteria 1 and 8). Kept with the slot because the slot is a
    -- DECISION and can move, so the verdict derived from it has to move
    -- with it. NULL where there was nothing to judge with.
    classification text,
    -- APPEND-ONLY (REQ-PIPE-141 NFR 3; Keith, 2026-10-05: UPDATE and
    -- DELETE refused, TRUNCATE not). A re-file is a NEW row naming the
    -- decision that made it; the rule's own filing is the one row with no
    -- `refiled_by`, written once. A supply's CURRENT filing is its newest
    -- row - qa.filing_current below, read by everything.
    id          bigserial PRIMARY KEY,
    refiled_by  bigint
);

--   the rule files a supply ONCE (REQ-PIPE-104 criterion 2)
CREATE UNIQUE INDEX IF NOT EXISTS filing_once
    ON "{SCHEMA}".filing (dataset_id, supply_id) WHERE refiled_by IS NULL;

CREATE OR REPLACE FUNCTION "{SCHEMA}".filing_is_append_only()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'qa.filing is append-only: a % is not permitted. A re-file is a new row '
        'naming its decision (REQ-PIPE-141)', TG_OP;
END $$;
DROP TRIGGER IF EXISTS filing_append_only ON "{SCHEMA}".filing;
CREATE TRIGGER filing_append_only
    BEFORE UPDATE OR DELETE ON "{SCHEMA}".filing
    FOR EACH STATEMENT EXECUTE FUNCTION "{SCHEMA}".filing_is_append_only();

-- A SUPPLY'S CURRENT FILING, DEFINED ONCE (REQ-PIPE-141 criterion 2 and
-- NFR 6): its newest row. Every reader of "the" filing reads this.
CREATE OR REPLACE VIEW "{SCHEMA}".filing_current AS
SELECT DISTINCT ON (dataset_id, supply_id) *
FROM "{SCHEMA}".filing
ORDER BY dataset_id, supply_id, id DESC;

--   one dataset's filings, at a cost that does not grow with any other
--   dataset's history - the per-dataset shape REQ-PIPE-034 established
--   for arrivals, which the retired directory layout gave for free.
CREATE INDEX IF NOT EXISTS filing_dataset
    ON "{SCHEMA}".filing (dataset_id, recorded_at);

--   "what is filed against this slot", which is what a held or
--   contested supply is judged against.
CREATE INDEX IF NOT EXISTS filing_slot
    ON "{SCHEMA}".filing (dataset_id, slot) WHERE slot IS NOT NULL;

-- A SUPPLY'S RECEIPT, DEFINED ONCE (REQ-PIPE-144 criteria 12 and 16).
-- The receipt of the supply's file in its linked delivery. Since
-- REQ-PIPE-105 a supply is one file with one receipt and this simply
-- returns it; only a CONTESTED pair (two files for one dataset in one
-- delivery) has two, and the view takes the earlier by instant then
-- receipt sequence - the same choice the arrival made (REQ-GEN-044
-- criterion 12), so the receipt and the supply id can never disagree.
-- Every "when was this supply received" reads this, and nothing else
-- re-derives the earlier-file rule.
CREATE OR REPLACE VIEW "{SCHEMA}".supply_receipt AS
SELECT DISTINCT ON (f.dataset_id, f.supply_id)
       f.dataset_id, f.supply_id, f.delivery, df.filename,
       df.received_at, df.received_instant, df.received_from, df.receipt_sequence,
       -- BESIDE the receipt, never it (REQ-PIPE-103 criterion 19).
       df.originally_received_stated
FROM "{SCHEMA}".filing_current f
JOIN "{SCHEMA}".delivery_file df
  ON df.delivery = f.delivery AND df.dataset_id = f.dataset_id
ORDER BY f.dataset_id, f.supply_id, df.received_instant, df.receipt_sequence, df.filename;

-- WHICH DATASETS MATCHED MORE THAN ONE FILE OF A DELIVERY (REQ-PIPE-144
-- criterion 26), derived from delivery_file rather than stored beside it
-- (criterion 25). Ordered as delivery_log.records() has always returned
-- it: by dataset, each dataset's files sorted by name.
CREATE OR REPLACE VIEW "{SCHEMA}".delivery_contested AS
SELECT delivery, dataset_id, array_agg(filename ORDER BY filename) AS files
FROM "{SCHEMA}".delivery_file
WHERE dataset_id IS NOT NULL
GROUP BY delivery, dataset_id
HAVING count(*) > 1;

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
-- THE CENSUS (REQ-PIPE-081 criteria 12 to 16): the decision log and the
-- warehouse compared, with only the DISCREPANCIES kept - normally none. A
-- census row says one was taken, of which periods (NULL: all), and why;
-- an "as at T" answer reads the last one taken on or before T, never the
-- warehouse as it stands now (criterion 14).
CREATE TABLE IF NOT EXISTS "{SCHEMA}".census (
    id        bigserial PRIMARY KEY,
    taken_at  timestamptz NOT NULL DEFAULT now(),
    trigger   text NOT NULL,
    run_key   text,
    periods   text[]
);
CREATE TABLE IF NOT EXISTS "{SCHEMA}".census_discrepancy (
    census_id  bigint NOT NULL REFERENCES "{SCHEMA}".census ON DELETE CASCADE,
    kind       text NOT NULL CHECK (kind IN ('missing', 'wrong-kind', 'stray')),
    period     text NOT NULL,
    dataset_id text,
    table_name text NOT NULL,
    supply     text,
    detail     text NOT NULL
);

CREATE TABLE IF NOT EXISTS "{SCHEMA}".decision (
    id             bigserial PRIMARY KEY,
    agency_id      text NOT NULL,
    collection_id  text NOT NULL,
    dataset_id     text NOT NULL,
    -- THE KNOWN ACTIONS ARE CHECKED BY A NAMED CONSTRAINT BELOW, not
    -- inline. An inline CHECK gets a generated name, which is fine
    -- until the list grows: `CREATE TABLE IF NOT EXISTS` does nothing
    -- to an existing table, so an older database keeps the old list and
    -- refuses the new action while a fresh one accepts it. That
    -- happened on 2026-09-28 and cost a debugging round.
    action         text NOT NULL,
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
    recorded_at    timestamptz NOT NULL DEFAULT now(),
    -- THE PERIOD A SUBSTITUTION STANDS ON (REQ-PIPE-084 criterion 5),
    -- and it is a column rather than a reuse of `from_slot` because the
    -- two mean opposite things. `from_slot` is the period a supply is
    -- moving OUT OF, and promoted_into() reads it that way - recording
    -- the period stood on there would empty it, which is the one thing
    -- a substitution must never do to the period it depends on.
    --
    -- IN THE LOG RATHER THAN DERIVED from which schema holds the table.
    -- The criterion asks for the period pointed at to be RECORDED, and
    -- this table's whole claim is that it answers from itself: a
    -- reconstruction from the catalogue would go wrong the moment a
    -- supply moved, which is exactly when somebody reads it.
    stands_on      text,
    CHECK (action <> 'substitute' OR (stands_on IS NOT NULL AND to_slot IS NOT NULL)),
    CHECK (action <> 'de-substitute' OR from_slot IS NOT NULL)
);

-- See the load_outcome note above on why an added column needs this as
-- well as its place in the CREATE TABLE.
ALTER TABLE "{SCHEMA}".decision ADD COLUMN IF NOT EXISTS stands_on text;

-- AND THE CONSTRAINTS, which ADD COLUMN does not bring with it. Named
-- explicitly so they can be replaced rather than accumulated: an
-- anonymous CHECK gets a generated name and a second run adds a second
-- one.
-- The generated name the inline CHECK used to carry, on every database
-- created before it moved down here.
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_action_check;
-- EVERY DECISION NAMES A SLOT, except a refused promotion of a supply
-- filed to none (REQ-PIPE-151 criterion 3): "held - no open period" is a
-- refusal with no period to name. Named since schema 30; it was the inline
-- `decision_check`, which a CREATE TABLE IF NOT EXISTS could never relax.
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_check;
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_names_a_slot;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_names_a_slot
    CHECK (action = 'promotion-refused' OR from_slot IS NOT NULL OR to_slot IS NOT NULL);
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_action_known;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_action_known
    CHECK (action IN ('promote', 'reject', 'demote', 'refile',
                      'substitute', 'de-substitute',
                      'inherit', 'inherit-refused', 'un-inherit',
                      'promotion-withheld', 'mark-not-supplied', 'acknowledge',
                      'supersede', 'un-supersede', 'still-failing',
                      'promotion-refused'));
-- WHICH NEWER SUPPLY SUPERSEDED THIS ONE (REQ-PIPE-118 criterion 10).
-- Schema 22, additive. Schema 23 relaxed the shape for a PERSON's
-- supersession (REQ-PIPE-120), which names no newer supply - shipped first
-- without the bump, so a database already at 22 kept the old constraint
-- and refused every one (post-build-review #109, F2).
ALTER TABLE "{SCHEMA}".decision ADD COLUMN IF NOT EXISTS superseded_by text;
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_supersede_shape;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_supersede_shape
    CHECK (action <> 'supersede'
           OR (from_slot IS NOT NULL AND (superseded_by IS NOT NULL OR actor_kind = 'person')));
-- SPRINT 10's DECISION-LOG COLUMNS, ALL IN ONE VERSION (schema 27,
-- REQ-PIPE-130 NFR 6: every column the batch needs arrives in one bump,
-- because each bump costs a full regeneration).
--   table_name - the dataset's table, beside dataset_id, on every entry
--     (REQ-PIPE-130 criterion 10), so a period's _manifest needs no
--     dataset-to-table mapping of its own.
--   promoted_status - the supply's status at the moment it was promoted,
--     rule or person (criterion 11): a fact about the decision, fixed
--     when it was taken, never looked up later.
--   replaces / replacement_* - the promoted supply a rule's promotion
--     replaced, and the replacement setting it acted under, its level and
--     its version (REQ-PIPE-123 criterion 5).
--   caused_by_decision - the decision a rule's record follows from: the
--     grouped "still failing" shout after a re-evaluation (REQ-PIPE-121
--     criterion 12).
ALTER TABLE "{SCHEMA}".decision ADD COLUMN IF NOT EXISTS table_name text;
ALTER TABLE "{SCHEMA}".decision ADD COLUMN IF NOT EXISTS promoted_status text;
ALTER TABLE "{SCHEMA}".decision ADD COLUMN IF NOT EXISTS replaces text;
ALTER TABLE "{SCHEMA}".decision ADD COLUMN IF NOT EXISTS replacement_setting text;
ALTER TABLE "{SCHEMA}".decision ADD COLUMN IF NOT EXISTS replacement_level text;
ALTER TABLE "{SCHEMA}".decision ADD COLUMN IF NOT EXISTS replacement_version text;
ALTER TABLE "{SCHEMA}".decision ADD COLUMN IF NOT EXISTS caused_by_decision bigint;
-- caused_by_supply - the supply whose promotion opened the period an
--   INHERIT filled (REQ-TEST-150 criterion 6; Keith, 2026-10-06, over a
--   time window): what the kept-run report reads to say which inheritances
--   a kept arrival caused. NULL where a person opened the period. Schema 31.
ALTER TABLE "{SCHEMA}".decision ADD COLUMN IF NOT EXISTS caused_by_supply text;
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_caused_by_supply_shape;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_caused_by_supply_shape
    CHECK (caused_by_supply IS NULL OR action = 'inherit');
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_promoted_status_shape;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_promoted_status_shape
    CHECK (promoted_status IS NULL OR action = 'promote');
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_replacement_known;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_replacement_known
    CHECK (replacement_setting IS NULL
           OR replacement_setting IN ('never', 'green', 'green-or-amber'));
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_still_failing_shape;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_still_failing_shape
    CHECK (action <> 'still-failing'
           OR (actor_kind = 'rule' AND caused_by_decision IS NOT NULL AND reason IS NOT NULL));
-- THE AMBER SETTING A RULE ACTED UNDER (REQ-PIPE-122 criteria 5, 11 and
-- 19) - value, level and version - on every automatic promotion of an
-- amber supply and on the withheld note under hold. Schema 21, additive.
-- acknowledgement_owed is DERIVED from the value rather than stored beside
-- it, so the two can never disagree.
ALTER TABLE "{SCHEMA}".decision ADD COLUMN IF NOT EXISTS amber_setting text;
ALTER TABLE "{SCHEMA}".decision ADD COLUMN IF NOT EXISTS amber_level text;
ALTER TABLE "{SCHEMA}".decision ADD COLUMN IF NOT EXISTS amber_version text;
ALTER TABLE "{SCHEMA}".decision ADD COLUMN IF NOT EXISTS acknowledgement_owed boolean
    GENERATED ALWAYS AS (action = 'promote' AND amber_setting = 'promote-and-acknowledge') STORED;
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_amber_setting_known;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_amber_setting_known
    CHECK (amber_setting IS NULL
           OR amber_setting IN ('hold', 'promote-and-acknowledge', 'promote'));
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_acknowledge_shape;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_acknowledge_shape
    CHECK (action <> 'acknowledge'
           OR (actor_kind = 'person' AND to_slot IS NOT NULL AND reason IS NOT NULL));
-- A MARK AS NOT SUPPLIED names the period it accepts as missed and no
-- supply (REQ-PIPE-132, version 20).
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_mark_not_supplied_shape;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_mark_not_supplied_shape
    CHECK (action <> 'mark-not-supplied'
           OR (to_slot IS NOT NULL AND (supply IS NULL OR supply = '')));
-- A withheld promotion names the period it stood back from, which is
-- the same shape a promotion has - it is a record ABOUT that slot
-- rather than a change to it (REQ-PIPE-077 criterion 6).
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_withheld_shape;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_withheld_shape
    CHECK (action <> 'promotion-withheld' OR to_slot IS NOT NULL);
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_substitute_shape;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_substitute_shape
    CHECK (action <> 'substitute' OR (stands_on IS NOT NULL AND to_slot IS NOT NULL));
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_de_substitute_shape;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_de_substitute_shape
    CHECK (action <> 'de-substitute' OR from_slot IS NOT NULL);
-- An un-inheritance names the period whose view is being removed, the
-- same shape a de-substitution has and for the same reason: it leaves
-- that period unfilled rather than moving anything into it
-- (REQ-PIPE-099 criterion 3).
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_un_inherit_shape;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_un_inherit_shape
    CHECK (action <> 'un-inherit' OR from_slot IS NOT NULL);

--   criterion 11's question, asked of every demote, reject and re-file:
--   does any period stand on this supply?
CREATE INDEX IF NOT EXISTS decision_stands_on
    ON "{SCHEMA}".decision (dataset_id, supply, effective_at)
    WHERE stands_on IS NOT NULL;

-- A REFUSAL HAS NO SUPPLY (REQ-PIPE-098 criterion 10), which is why the
-- NOT NULL on `supply` had to give way to a CHECK. The criterion asks
-- for an inheritance that could not complete to be RECORDED rather than
-- silent, and the thing it could not find is precisely a supply - so
-- there is nothing honest to put in that column.
--
-- NARROW ON PURPOSE. Every other action still requires one, enforced by
-- the CHECK below rather than by the column, so nothing else gains the
-- freedom to write a decision about nothing in particular.
ALTER TABLE "{SCHEMA}".decision ALTER COLUMN supply DROP NOT NULL;
ALTER TABLE "{SCHEMA}".decision DROP CONSTRAINT IF EXISTS decision_supply_present;
ALTER TABLE "{SCHEMA}".decision ADD CONSTRAINT decision_supply_present
    CHECK (action IN ('inherit-refused', 'mark-not-supplied', 'still-failing')
           OR (supply IS NOT NULL AND supply <> ''));

--   WHEN A PERIOD WAS OPENED (REQ-PIPE-098 criterion 3). "First
--   created" has to be a FACT rather than an inference from the schema
--   being present, because inheritance happens once, at that moment,
--   and an inference cannot tell a period opened a moment ago from one
--   opened last year whose schema was dropped and rebuilt.
--
--   ASSET-LEVEL, not per dataset: a period schema holds every dataset's
--   tables, so it is opened once and every dataset inherits into it.
CREATE TABLE IF NOT EXISTS "{SCHEMA}".period (
    name       text PRIMARY KEY,
    -- WHY IT WAS OPENED, and the two ways are deliberately
    -- indistinguishable afterwards (criterion 4): a period opened by
    -- instruction must behave exactly like one created by a first
    -- promotion, so this is a fact about history rather than a mode.
    opened_by  text NOT NULL CHECK (opened_by <> ''),
    opened_at  timestamptz NOT NULL DEFAULT now()
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

-- A SUPPLY NOTHING COULD PLACE, KEPT UNTIL SOMEBODY PLACES IT
-- (REQ-PIPE-078). A hold used to live for exactly as long as the run
-- that raised it: `file_arrivals()` skipped a held dataset with a
-- `continue` and said nothing, and `supply_holds.py` aggregated the
-- run's own assignments in memory and threw them away. The state a
-- person was meant to drain was a message that scrolled past.
--
-- MUTABLE, AND SAYING SO IS REQUIRED (NFR 4). The `filing` table above
-- is write-once because a filing must never be re-derived against a
-- schedule that has moved on. This one is the opposite discipline on
-- purpose: a row is RAISED once and RESOLVED once, and the resolution
-- is an UPDATE. Two records that look alike and are governed by
-- opposite rules is exactly the pair worth naming rather than leaving
-- for a reader to infer from the absence of a trigger.
--
-- WHY NOT A NULL SLOT IN `filing`. Both kinds of hold have to land on
-- the same terms (criterion 3), and a delivery-level hold has no
-- filing to hang off: REQ-PIPE-059 refuses to choose between two files
-- for one dataset, so nothing was filed and writing a filing row would
-- be making that choice by another route. The assignment-rule hold
-- keeps its `filing` row - that row is evidence of what the rule saw,
-- which is the thing `filing` is for - and the open work item lives
-- here, where it can be closed.
CREATE TABLE IF NOT EXISTS "{SCHEMA}".hold (
    dataset_id  text NOT NULL,
    supply_id   text NOT NULL,
    -- WHICH RULE DECLINED. The two are resolved differently - a
    -- delivery-level hold needs somebody to say which FILE is the
    -- supply, an assignment-rule one needs somebody to say which SLOT
    -- it fills - so the kind is what a queue turns into an instruction.
    kind        text NOT NULL CHECK (kind <> ''),
    -- WHY, as the producing rule saw it: the competing filenames, or
    -- each slot considered and what made it unavailable. A hold that
    -- says only "no slot" tells a person nothing they can act on, and
    -- acting on it is the entire point (REQ-PIPE-064 criterion 4).
    reason      jsonb NOT NULL DEFAULT '{{}}',
    -- THE RUN THAT RAISED IT (criterion 1). Not a foreign key to
    -- `qa.run`: every other table here cascades from a run and a hold
    -- deliberately does not, for the reason `decision` does not either
    -- - regenerating QA history must not silently drop the work queue.
    raised_by   text NOT NULL,
    delivery    text,
    raised_at   timestamptz NOT NULL DEFAULT now(),
    -- WHICH DECISION CLOSED IT (criterion 6). A hold is not cleared by
    -- a later run passing over it (criterion 2) - only an entry in the
    -- log ends one, and the row keeps pointing at it afterwards so
    -- "why is this no longer waiting on me" is answerable.
    resolved_by bigint REFERENCES "{SCHEMA}".decision (id),
    resolved_at timestamptz,
    PRIMARY KEY (dataset_id, supply_id),
    CONSTRAINT hold_resolution_is_whole
        CHECK ((resolved_by IS NULL) = (resolved_at IS NULL))
);

--   COUNTING AND GROUPING WITHOUT READING ONE ROW PER SUPPLY
--   (criterion 8), which is a scale requirement rather than a
--   micro-optimisation: at ~30 datasets a queue that loads every held
--   supply to say how many there are is the same design that turns one
--   banner into thirty.
CREATE INDEX IF NOT EXISTS hold_outstanding
    ON "{SCHEMA}".hold (dataset_id, kind) WHERE resolved_by IS NULL;

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

-- A SUPPLY'S CURRENT RUN, DEFINED ONCE (REQ-PIPE-140 criterion 5): its
-- newest COMPLETED run of its own checks - an arrival's or a re-run's,
-- never a readers-only one, which is not about the supply. The gate, the
-- dashboard and the terminal read a supply's verdict from this run;
-- every earlier run stays in qa.run as history.
--
-- NEWEST ON THE ASSET'S TIMELINE (Keith, 2026-10-06, post-build-review #117
-- D6): a re-run by when the decision that caused it took effect, an
-- arrival's run by when its supply was received, the run's own instant only
-- where neither is known - the order supply_status.runs_about already used.
-- It was the wall clock, which a replay stamps in processing order, so the
-- two definitions named different runs current.
-- DROP first: CREATE OR REPLACE VIEW cannot reorder a view's columns.
DROP VIEW IF EXISTS "{SCHEMA}".supply_current_run;
CREATE VIEW "{SCHEMA}".supply_current_run AS
SELECT DISTINCT ON (r.dataset_id, r.supply_id) r.*
FROM "{SCHEMA}".run_visible r
LEFT JOIN "{SCHEMA}".decision d ON d.id = r.caused_by_decision
LEFT JOIN "{SCHEMA}".supply_receipt rc
    ON rc.dataset_id = r.dataset_id AND rc.supply_id = r.supply_id
WHERE r.supply_id IS NOT NULL AND r.scope <> 'readers'
ORDER BY r.dataset_id, r.supply_id,
         COALESCE(d.effective_at, rc.received_instant, r.run_instant) DESC,
         -- A TIE GOES TO THE LATER RUN, then the key (Keith, 2026-10-06,
         -- post-build-review #122 D6): keys sort as text, `__r10` before
         -- `__r9`. Schema 32.
         r.run_instant DESC,
         r.run_key DESC;

-- A RE-RUN THAT IS OWED (REQ-PIPE-140 criterion 7). Recorded in the
-- transaction of the decision (or the load) that causes it, and cleared
-- only once the run has completed AND the gate has been applied to it -
-- so a crash between the two leaves it owed rather than lost.
--
-- IT CHANGES STATE ON PURPOSE, as qa.hold does: raised once, attempted,
-- cleared once. It is a work item, not history - the history is the
-- decision that caused it and the run that discharged it.
CREATE TABLE IF NOT EXISTS "{SCHEMA}".owed_run (
    id                 bigserial PRIMARY KEY,
    -- `recheck` - a supply's own checks again (REQ-PIPE-140 criterion 1);
    -- `reevaluate` - only the readers of `tables` in `period` (criterion 2).
    kind               text NOT NULL CHECK (kind IN ('recheck', 'reevaluate')),
    dataset_id         text NOT NULL,
    supply_id          text,
    period             text,
    tables             text[] NOT NULL DEFAULT '{{}}',
    caused_by_decision bigint,
    caused_by_load     bigint,
    owed_at            timestamptz NOT NULL DEFAULT now(),
    -- The run id minted on the first attempt, so a retry completes the
    -- same run rather than leaving a trail of half-runs.
    run_key            text,
    attempts           integer NOT NULL DEFAULT 0,
    last_failure       text,
    cleared_at         timestamptz,
    cleared_by_run     text,
    CHECK ((caused_by_decision IS NULL) <> (caused_by_load IS NULL)),
    CHECK ((cleared_at IS NULL) = (cleared_by_run IS NULL))
);

--   "what is owed", the only question asked of it routinely
CREATE INDEX IF NOT EXISTS owed_run_open
    ON "{SCHEMA}".owed_run (owed_at) WHERE cleared_at IS NULL;

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

-- WHAT EACH SLOT HOLDS, DEFINED ONCE (REQ-PIPE-130 criteria 8 and 9).
-- Every question of what a slot holds or held - the gate's filled-slot
-- check, slot states, the stood-on guard, the newest promoted supply, the
-- drift reference - is answered from here, and from nowhere else. Five
-- Python readers used to take "the latest decision naming the slot",
-- and that rule was wrong three ways (post-build-review #75, #84, #85):
-- a refusal (promotion-withheld, inherit-refused) names a period without
-- changing it, and a reject, demote or re-file names ITS OWN supply's
-- slot whichever supply that is - rejecting an unpromoted resupply of a
-- filled period is not a decision about what fills it.
--
-- So the slot's decisions are WALKED in effective order. An entry INTO
-- the slot sets how it is held and by what: `held_as` is promoted (a
-- promote or re-file), substituted or inherited, and `holder` the supply.
-- An entry OUT OF it empties it, except a reject, demote or re-file
-- naming a supply OTHER than the holder, which changes nothing. Refusals
-- are not read at all. `fills` is the holder where the slot is FILLED -
-- promoted or substituted; an inherited period is one the dataset does
-- not take part in, so it has no slot to fill (REQ-PIPE-084 criteria 4
-- and 7). Readers ask `held_as` and never interpret an action
-- themselves: a re-file OUT leaves its action as the slot's last
-- decision, and reading 'refile' as "holds a supply" is how an emptied
-- slot read as promoted (delivery-critic, sprint 2). `decision_id` is the last entry that
-- CHANGED the slot, which is what a slot's state and its "decided by"
-- are read from. `as_at` filters on effective_at (what the warehouse
-- held then), never on recorded_at.
--
-- A FUNCTION RATHER THAN A PLAIN VIEW so the as-at form and the
-- one-dataset form are the same definition; slot_holds_now is the view
-- for a reader that wants the present over every dataset.
DROP VIEW IF EXISTS "{SCHEMA}".slot_holds_now;
DROP FUNCTION IF EXISTS "{SCHEMA}".slot_holds(text, timestamptz);
CREATE FUNCTION "{SCHEMA}".slot_holds(for_dataset text, as_at timestamptz)
RETURNS TABLE (dataset_id text, slot text, decision_id bigint, fills text,
               held_as text, holder text)
LANGUAGE sql STABLE AS $fn$
WITH RECURSIVE named AS (
    SELECT d.id, d.dataset_id, s.slot, d.action, d.supply, d.to_slot,
           row_number() OVER (PARTITION BY d.dataset_id, s.slot
                              ORDER BY d.effective_at, d.id) AS rn
    FROM "{SCHEMA}".decision d
    CROSS JOIN LATERAL (SELECT d.to_slot AS slot UNION SELECT d.from_slot) s
    WHERE s.slot IS NOT NULL
      AND (for_dataset IS NULL OR d.dataset_id = for_dataset)
      AND (as_at IS NULL OR d.effective_at <= as_at)
      -- ONLY DECISIONS THAT CHANGE A SLOT, listed rather than the
      -- refusals excluded, so an annotating decision added later
      -- (REQ-PIPE-132's acknowledgements, a re-check record) is ignored
      -- until somebody decides it changes a slot - never read as one by
      -- default.
      AND d.action IN ('promote', 'refile', 'substitute', 'inherit',
                       'reject', 'demote', 'de-substitute', 'un-inherit')
      -- A RE-FILE NEVER FILLS THE SLOT IT GOES TO (REQ-PIPE-141 criteria
      -- 4 and 9): the supply waits in staging there, checked again, and
      -- the gate decides - so only its leaving the OLD slot is a step.
      AND NOT (d.action = 'refile' AND s.slot = d.to_slot)
), step AS (
    -- What one entry does to a slot, given what the slot held before:
    -- `skips` where it is about a supply other than the one holding it.
    SELECT n.*,
           -- IS NOT DISTINCT FROM, never `=`: a reject's to_slot is NULL,
           -- and `NULL = slot` is NULL rather than false, which made
           -- every "about another supply" skip below silently not fire.
           (n.to_slot IS NOT DISTINCT FROM n.slot) AS into_slot
    FROM named n
), walk AS (
    SELECT n.dataset_id, n.slot, n.rn, n.id AS last_id,
           CASE WHEN n.into_slot THEN CASE n.action
                WHEN 'promote' THEN 'promoted'
                WHEN 'substitute' THEN 'substituted' WHEN 'inherit' THEN 'inherited'
                END END AS held_as,
           CASE WHEN n.into_slot THEN n.supply END AS holder
    FROM step n WHERE n.rn = 1
    UNION ALL
    SELECT n.dataset_id, n.slot, n.rn,
           CASE WHEN NOT n.into_slot AND n.action IN ('reject', 'demote', 'refile')
                     AND w.holder IS NOT NULL AND n.supply <> w.holder
                THEN w.last_id ELSE n.id END,
           CASE WHEN n.into_slot THEN CASE n.action
                WHEN 'promote' THEN 'promoted'
                WHEN 'substitute' THEN 'substituted' WHEN 'inherit' THEN 'inherited'
                END
                WHEN n.action IN ('reject', 'demote', 'refile')
                     AND w.holder IS NOT NULL AND n.supply <> w.holder
                THEN w.held_as END,
           CASE WHEN n.into_slot THEN n.supply
                WHEN n.action IN ('reject', 'demote', 'refile')
                     AND w.holder IS NOT NULL AND n.supply <> w.holder
                THEN w.holder END
    FROM walk w
    JOIN step n ON n.dataset_id = w.dataset_id AND n.slot = w.slot
               AND n.rn = w.rn + 1
)
SELECT DISTINCT ON (w.dataset_id, w.slot)
       w.dataset_id, w.slot, w.last_id,
       CASE WHEN w.held_as IN ('promoted', 'substituted') THEN w.holder END,
       w.held_as, w.holder
FROM walk w
ORDER BY w.dataset_id, w.slot, w.rn DESC
$fn$;

CREATE VIEW "{SCHEMA}".slot_holds_now AS
SELECT * FROM "{SCHEMA}".slot_holds(NULL, NULL);

-- WHAT A PERIOD HOLDS AND HOW IT GOT THERE (REQ-PIPE-130), the one
-- definition every period's `_manifest` view is a thin call on. WHAT is in
-- the schema comes from the catalogue - one row per table or view actually
-- present (criterion 2) - and WHY from qa.slot_holds, the filings' receipt
-- view and the promotion entry (criterion 7): never a maintained table.
--
-- SECURITY DEFINER, so a reader granted only a period schema reads its
-- `_manifest` without any grant on this metadata schema (NFR 2), and sees
-- only these columns. search_path is pinned, with pg_temp LAST - left off,
-- pg_temp is searched first and a caller's temporary pg_class could spoof
-- the listing (post-build-review #116, D5; schema 28).
--
-- decided_by is ONLY 'rule' or 'person', never a name (criterion 5).
-- promoted_status is what the supply was promoted on - for an inherited or
-- substituted table, the supply it stands on - and never its health since
-- (criteria 11 and 12). acknowledged is NULL where none was owed (6).
CREATE OR REPLACE FUNCTION "{SCHEMA}".manifest_for(for_period text, for_schema text)
RETURNS TABLE (table_name text, dataset_id text, kind text, supply text,
               received_at timestamptz, from_period text, decided_at timestamptz,
               decided_by text, acknowledged boolean, reason text, promoted_status text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $fn$
WITH present AS (
    SELECT c.relname::text AS table_name
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = for_schema AND c.relkind IN ('r', 'v', 'm', 'p', 'f')
      AND c.relname <> '_manifest'
), held AS (
    SELECT h.dataset_id, h.held_as, h.holder, d.table_name, d.effective_at,
           d.actor_kind, d.reason, d.stands_on
    FROM "{SCHEMA}".slot_holds(NULL, NULL) h
    JOIN "{SCHEMA}".decision d ON d.id = h.decision_id
    WHERE h.slot = for_period AND h.held_as IS NOT NULL
)
SELECT p.table_name, h.dataset_id, h.held_as, h.holder, r.received_instant,
       CASE WHEN h.held_as = 'promoted' THEN NULL ELSE h.stands_on END,
       h.effective_at, h.actor_kind,
       CASE WHEN pr.acknowledgement_owed THEN EXISTS (
           SELECT 1 FROM "{SCHEMA}".decision a
           WHERE a.action = 'acknowledge' AND a.dataset_id = h.dataset_id
             AND a.supply = h.holder AND a.to_slot = pr.to_slot) END,
       h.reason, pr.promoted_status
FROM present p
LEFT JOIN held h ON h.table_name = p.table_name
LEFT JOIN "{SCHEMA}".supply_receipt r
       ON r.dataset_id = h.dataset_id AND r.supply_id = h.holder
LEFT JOIN LATERAL (
    SELECT x.promoted_status, x.acknowledgement_owed, x.to_slot
    FROM "{SCHEMA}".decision x
    WHERE x.action = 'promote' AND x.dataset_id = h.dataset_id AND x.supply = h.holder
    ORDER BY x.effective_at DESC, x.id DESC LIMIT 1) pr ON true
ORDER BY p.table_name
$fn$;
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
        # REFUSED BEFORE ANY DDL RUNS - both directions, from one place
        # (REQ-PIPE-144 criterion 40). Applying this checkout's DDL over a
        # NEWER schema and then recording our own version was a silent
        # downgrade (post-build-review #79); applying it over one older
        # than RESHAPED_AT would half-apply it.
        _refuse_another_version(_recorded_version(conn))
        conn.raw.execute(DDL)
        # The period-table guard (REQ-PIPE-129 criterion 11) - installed
        # with the schema it lives in, and reported rather than raised
        # where the platform withholds the rights (criterion 18).
        from qa_tools.common import period_tables
        period_tables.install_guard(conn)
        conn.execute(
            f'INSERT INTO "{SCHEMA}".schema_version (version) VALUES (?) '
            "ON CONFLICT (only_row) DO UPDATE SET version = EXCLUDED.version",
            [SCHEMA_VERSION])
    finally:
        conn.execute("SELECT pg_advisory_unlock(?)", [_DDL_LOCK])


def _recorded_version(conn: supply_db.SupplyConnection) -> int | None:
    """The version this database's qa schema records, or None where it
    has none yet (an empty database)."""
    if not conn.execute(
            f"SELECT to_regclass('{SCHEMA}.schema_version')").fetchall()[0][0]:
        return None
    rows = conn.execute(f'SELECT version FROM "{SCHEMA}".schema_version').fetchall()
    return rows[0][0] if rows else None


def _refuse_another_version(recorded: int | None) -> None:
    """Raise where this checkout must not apply its DDL over `recorded`."""
    if recorded is None or recorded == SCHEMA_VERSION:
        return
    if recorded > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"this database's qa schema is version {recorded}, NEWER than this "
            f"checkout's {SCHEMA_VERSION}. Refusing rather than applying older "
            f"definitions over it and rewriting the version down - update this "
            f"checkout, or point it at a database of its own version.")
    # EVERY OLDER VERSION IS REFUSED, not only one from before a reshape
    # (Keith, 2026-10-05: always wipe and rebuild). Regenerate, never
    # migrate - schemas 19 to 23 had been applied in place as additive
    # changes, which this rule never allowed.
    why = (f"from before the version-{RESHAPED_AT} reshape of qa.filing and "
           f"qa.delivery" if recorded < RESHAPED_AT else
           f"older than this checkout's {SCHEMA_VERSION}")
    raise SchemaVersionError(
        f"this database's qa schema is version {recorded}, {why}, and a schema "
        f"is never brought up to date in place. Rebuild it from an empty database: "
        f"`mothman env reset-synthetic`, then `mothman pipeline bootstrap`.")


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

def set_run_purpose(conn: supply_db.SupplyConnection, run_key: str, *,
                    dataset_id: str | None, supply_id: str | None,
                    scope: str = "arrival", period: str | None = None,
                    reads_table: str | None = None, caused_by_decision: int | None = None,
                    caused_by_load: int | None = None) -> None:
    """What a run is for (REQ-PIPE-140): whose supply, which scope, and -
    for a re-run - what caused it. Stated on the run rather than read off
    its id, which says whose table it is and nothing more."""
    conn.execute(
        f'UPDATE "{SCHEMA}".run SET dataset_id = ?, supply_id = ?, scope = ?, period = ?, '
        "reads_table = ?, caused_by_decision = ?, caused_by_load = ? WHERE run_key = ?",
        [dataset_id, supply_id, scope, period, reads_table, caused_by_decision,
         caused_by_load, run_key])


def current_run(conn: supply_db.SupplyConnection, dataset_id: str,
                supply_id: str) -> str | None:
    """The supply's current run (REQ-PIPE-140 criterion 5): its newest
    completed run of its own checks. Earlier runs stay as history."""
    rows = conn.execute(
        f'SELECT run_key FROM "{SCHEMA}".supply_current_run '
        "WHERE dataset_id = ? AND supply_id = ?", [dataset_id, supply_id]).fetchall()
    return rows[0][0] if rows else None


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
        "environment, tool_versions, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
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
         environment, json.dumps(dict(tool_versions or {})), _stamp()])


def _stamp():
    """Now - or the replay's own time in a replay of a synthetic history
    (REQ-PIPE-081 criteria 27-31)."""
    from qa_tools.common import replay_clock
    return replay_clock.now()


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
        f'UPDATE "{SCHEMA}".run SET completed_at = ? '
        "WHERE run_key = ? AND run_by IS NOT NULL AND environment IS NOT NULL "
        "RETURNING run_key", [_stamp(), run_key]).fetchall()
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


def register_run_if_absent(conn: supply_db.SupplyConnection, *, run_key: str,
                           agency_id: str, collection_id: str, run_timestamp: str) -> None:
    """Register a run that does not exist yet, and touch nothing about one
    that does. For a writer that runs BEFORE the orchestrator opens the
    run - file checks at staging - where record_run's update of the
    timestamp would be wrong: the orchestrator's own is the one that
    counts."""
    conn.execute(
        f'INSERT INTO "{SCHEMA}".run (run_key, agency_id, collection_id, run_timestamp, '
        "run_instant, created_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (run_key) DO NOTHING",
        [run_key, agency_id, collection_id, run_timestamp, run_timestamp, _stamp()])


def record_file_results(conn: supply_db.SupplyConnection, run_key: str,
                        results: Sequence[Mapping[str, Any]], *, agency_id: str,
                        collection_id: str, supply_state: str, load_attempt: int,
                        delivery: str, filename: str) -> int:
    """Record one load attempt's file-check results (REQ-QAC-096).

    APPENDS, NEVER REPLACES - the one writer here that does not delete
    first, and deliberately: a reprocessed file is evaluated again and
    both attempts' results are kept (criteria 7 and 16), told apart by
    `load_attempt`. record_results() replaces by (run, tool, scope,
    state), which would quietly keep only the latest attempt - the
    alternative Keith rejected.
    """
    columns = ("run_key", *_RESULT_COLUMNS, *_KEY_COLUMNS, "load_attempt", "delivery",
               "filename", "extra")
    placeholders = ", ".join(["?"] * len(columns))
    keys = (agency_id, collection_id, "file", FILE_SCOPE, supply_state)
    ignored = set(_RESULT_COLUMNS) | set(_KEY_COLUMNS)
    for record in results:
        values = [record.get(name) for name in _RESULT_COLUMNS]
        extra = {k: v for k, v in record.items() if k not in ignored}
        conn.execute(
            f'INSERT INTO "{SCHEMA}".check_result ({", ".join(columns)}) '
            f"VALUES ({placeholders})",
            [run_key, *values, *keys, load_attempt, delivery, filename,
             json.dumps(extra, default=str)])
    return len(results)


def record_tool_output(conn: supply_db.SupplyConnection, run_key: str, tool: str,
                       raw_output: Any, dataset_id: str | None = None) -> None:
    """Keep a tool's own unmodified payload."""
    conn.execute(
        f'INSERT INTO "{SCHEMA}".tool_output (run_key, tool, dataset_id, raw_output) '
        "VALUES (?, ?, ?, ?) ON CONFLICT (run_key, tool, dataset_id) "
        "DO UPDATE SET raw_output = EXCLUDED.raw_output",
        [run_key, tool, dataset_id or "", json.dumps(raw_output, default=str)])


def record_tables_read(conn: supply_db.SupplyConnection, run_key: str,
                       resolved: Mapping[str, str],
                       supplies: Mapping[str, str] | None = None) -> None:
    """Record which physical table each logical name resolved to, and -
    for a period table - which supply it held (REQ-PIPE-129 criterion 13)."""
    supplies = supplies or {}
    for logical, physical in sorted(resolved.items()):
        conn.execute(
            f'INSERT INTO "{SCHEMA}".tables_read '
            "(run_key, logical_table, physical_table, supply) "
            "VALUES (?, ?, ?, ?) ON CONFLICT (run_key, logical_table) "
            "DO UPDATE SET physical_table = EXCLUDED.physical_table, "
            "supply = EXCLUDED.supply",
            [run_key, logical, physical, supplies.get(logical)])


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
