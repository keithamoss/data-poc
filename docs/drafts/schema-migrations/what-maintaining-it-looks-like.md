# What maintaining schema migrations would look like

A draft for Keith (plans/running-thoughts.md #89), written 2026-10-14 so he
can get a feel for the day-to-day before choosing a tool. Decided already:
versioned, forward-only migrations, from now (version 41 onwards), version 40
as the baseline, applied by an explicit `mothman db migrate`, proved both in
CI and by a dry run on a copy of the real database. Still open: the tool -
our own runner or Alembic with alembic_utils.

Scope: the QA metadata schema only (`qa`: filings, decisions, verdicts,
runs, results, holds and their views and triggers). A contract changing a
dataset's own columns is a separate question (running-thoughts #94).

## How often it happens

Measured from git: 38 version bumps in 17 days (27 September to 13 October
2026), up to 8 in one day. The fifteen most recent were mostly:

- a new table, often with its own append-only trigger and trigger function;
- new columns on an existing table;
- a view replaced or redefined;
- the occasional reshape that moves data between tables.

That is a PoC still finding its model. A production asset changes when a
release changes the model, which should be a handful of migrations per
release rather than several a day. Every one of them still runs against
history nobody can regenerate.

## The four kinds of change, worked through

Each shows what a developer does, what CI does, and what happens in
production. Where the two tools differ, both are shown.

### 1. Add a column (the commonest)

Example: `qa.hold` gains `resolved_by text`.

**Developer, own runner.** Edit the table definition in the schema file (so a
fresh build has it), then add `migrations/041_hold_resolved_by.sql`:
`ALTER TABLE qa.hold ADD COLUMN resolved_by text;`. Bump the version to 41.

**Developer, Alembic.** Edit the table's SQLAlchemy definition, run
`alembic revision --autogenerate -m "hold resolved_by"`, and read the
generated file: it should say `op.add_column("hold", ...)`. Commit both.

**CI, either tool.** Build a database at version 40, apply the migration,
build a fresh one at version 41, and compare the two schemas: tables,
columns, indexes, views, triggers and functions. They must be identical. It
also checks that every row present before is still present, unchanged.

**Production.** Someone runs `mothman db migrate` against a copy of the real
database first, and the same comparison runs there. Then, in a quiet window,
it runs for real: the command prints the SQL it will run (Alembic: `--sql`),
asks for the typed confirmation used elsewhere in mothman, applies it in one
transaction, and records version 41. Until then, every other command refuses
the database, naming `mothman db migrate`.

### 2. Change a view

Example: `qa.filing_current` gains a column.

**Own runner.** The migration repeats the view's full new definition
(`CREATE OR REPLACE VIEW ...`, or drop and recreate if columns move). The
easy mistake is editing the schema file and forgetting the migration; the CI
comparison catches it.

**Alembic + alembic_utils.** The view is registered as an entity, and
autogenerate notices the definition changed and writes the replace for you.
This is where the generator earns its keep.

### 3. A new table with its own trigger (the recent norm)

Example: a new append-only `qa.correction_parked_resolved`.

**Own runner.** The migration creates the table, the trigger function and the
trigger, copied from the schema file. About thirty lines, all SQL that already
exists.

**Alembic + alembic_utils.** The table is a SQLAlchemy definition, and the
function and trigger are registered entities; autogenerate writes all three.

### 4. A reshape that moves data (rare, and the one that matters)

Example: splitting one table's column into a table of its own, as
`qa.filing` was reshaped on 4 October.

**Either tool.** Nothing generates this: the migration is hand-written.
Create the new table, copy the rows across, drop the old column. That is
also where a real asset can lose history if the migration is wrong. Hence
the dry run on a copy, and a backup taken immediately before. Forward-only
means a bad migration is fixed by restoring that backup, not by running a
"down" script.

## Who does what, in a team

- **The developer** writes the migration in the same change that alters the
  schema. The version number is the only thing that conflicts when two
  people both add a migration on separate branches, and the second to merge
  renumbers theirs. Alembic's revision chain flags the clash at merge.
- **The reviewer** reads the migration SQL, not just the schema change: it is
  the part that runs on real history.
- **CI** builds from the previous version and compares, on every push.
- **Whoever runs production** takes a backup, dry-runs on a copy, then runs
  `mothman db migrate` in a quiet window - with the processing loop stopped,
  since a migration takes locks the loop would wait on.

## The two tools, side by side

| | Own runner | Alembic + alembic_utils |
|---|---|---|
| Writing a migration | By hand, as SQL | Generated, then reviewed; a reshape is hand-written in both |
| Forgotten migration | Caught by the CI comparison | Generation shows it; CI catches it too |
| Clash between branches | Two files claim the same number | Revision chain flags the second head at merge |
| Production review | `mothman db migrate` prints the SQL | `--sql` prints scripts a DBA knows |
| Up-front cost | About 100 lines of runner | Re-expressing ~1,500 lines of schema SQL as SQLAlchemy definitions and registered entities; three dependencies |
| Familiar to a new team | No | Yes, widely used |

## What is not decided yet

- The tool.
- Whether `mothman db migrate` also covers the per-database guard and the
  identity row, which live in the same schema.
- REQ-PIPE-144's "always wipe and rebuild on a schema change" (Keith,
  2026-10-05) is reversed by the "from now" answer and gets amended when this
  is scoped and signed.
