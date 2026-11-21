# Schema migrations and raw evidence: parked for a later call

**Status: PARKED (Keith, 2026-10-14).** "This is a bigger change that we
need to think about ... write this all up ... and we'll make a call later on
this much wider set of changes." Nothing here is scoped into requirements or
signed. Source item: plans/running-thoughts.md #89; the dataset-columns
question is split out as #94.

The documents beside this one hold the detail:

- `what-maintaining-it-looks-like.md` - the day-to-day of running migrations
  in a team, change kind by change kind.
- `schema-bumps-analysis.md` - all 38 real schema version bumps, classified:
  could each have been migrated in place, and would it have needed QA re-run?
- `raw-evidence-audit.md` - where we store a derived value without the raw
  evidence it came from (rule 3 below).

## The problem

The QA metadata schema (`qa`) is at version 40 after 38 bumps in 17 days.
Today any older database is refused, and the only remedy is to delete
everything (`mothman env reset-synthetic`) and bootstrap again - which refuses
an asset that is not synthetic. So a real asset would be stuck after its
first schema change. What a real asset cannot regenerate: the append-only
decision log, verdicts (recorded facts, REQ-PIPE-168), write-once filings and
receipts, and the supply rows. Replaying deliveries would re-judge history
with today's code.

## Decided so far (Keith, 2026-10-14)

| Question | Answer |
|---|---|
| Mechanism | Versioned, forward-only migrations, each applied in order in one transaction. Rejected: replaying deliveries (re-judges verdicts); additive-only in place (boxes in reshapes). |
| When | From now: every bump from version 41 ships a migration and its test. This reverses REQ-PIPE-144's 2026-10-05 "always wipe and rebuild". |
| Proof | Both: CI tests each migration on a database built at the previous version, and a dry run on a copy of the real database before production. |
| Scope | The `qa` metadata schema only. A contract changing a dataset's own columns is separate (running-thoughts #94). |
| Baseline | Version 40 is migration zero; older databases are still refused with the rebuild message. |
| Applying | An explicit `mothman db migrate` that shows what it will apply; everything else refuses an older database and names that command. Rejected: automatic on connect. |
| reset-synthetic | Kept for regenerating a synthetic history; no longer the remedy for a schema gap. |
| Supply-row samples in `qa` | Move them supply-side, out of the publisher's reach; `qa` keeps counts and salted hashes of keys. |
| Where delivered files live | A versioned bucket in each asset's own account, the version id recorded at receipt. Retention to be scoped with the data custodians. |

## Still open

### The tool: Alembic or Django, tied

Keith: Alembic and Django are tied at the top. A runner of our own is
**rejected** - "we just end up reinventing models and migrations that
Alembic and Django already do really well". Rewriting the hand-written
schema SQL as real models is an accepted cost. More analysis to come.

What is known so far:

- **Alembic** works without ORM classes but needs SQLAlchemy table
  definitions to autogenerate. With **alembic_utils** (0.8.8) it also
  autogenerates PostgreSQL functions, views, materialized views, triggers and
  policies. `--sql` offline mode prints each upgrade's exact SQL for a DBA to
  review.
- **Django** migrations are generated from models. Triggers go into Django's
  own migrations through **django-pgtrigger** (4.17), and views through
  **django-pgviews-redux** (1.2.0). Both still need a model for everything,
  and Django is a whole web framework for a CLI and a static dashboard.
- Neither generates a reshape that moves data; that is always hand-written,
  and it is the kind that can lose history.
- Either way, migrations become a separate, deliberate deploy step, reversing
  the recorded "every writer self-migrates" (`ensure_schema`). Keith chose the
  explicit command, so this is settled in substance.

### Five design rules, proposed from the 38-bump analysis

None of the 38 bumps needed the QA tools re-run; the real risk is re-judging
history. These rules would have made the dangerous ones safe:

1. **An empty value means "not recorded at the time".** Never a default that
   claims a fact (version 19's `DEFAULT 'automated'` would have claimed every
   hand-filing was automated).
2. **Never recompute verdict-like values for history.** Leave them empty, or
   append a new row naming the code and configuration that computed it.
3. **Record the raw evidence when it happens**, so a new derived value can be
   filled from it later by a migration, not by re-running anything.
4. **Version the meaning of append-only facts.** When an action's meaning
   changes, give it a new name rather than re-reading old rows under the new
   rule (version 26: old re-files would silently read as leaving their slot
   empty).
5. **Reshape in stages**: add the new structure, fill it, verify old and new
   agree, then remove the old.

### Rule 3 gaps found in the PoC today (from `raw-evidence-audit.md`)

The three serious ones, each checked against the code or the database:

- **Recorded evidence can be overwritten.** A run's results are deleted and
  re-inserted, and tool output is overwritten in place, under a run's fixed
  key. A promotion can end up pointing at results that no longer match the
  status it was promoted on. Fix: keep each attempt, or refuse writes to a
  finished run.
- **No record of exactly which file was judged.** `qa.delivery_file` has no
  checksum, size or header row. Fix: record them at receipt, with the storage
  version id.
- **No code or tool versions.** `run.tool_versions` is empty on all 229 runs,
  and no commit hash is stored anywhere. Fix: fill it on every run, and record
  the code version on decisions, filings and verdicts.

The medium ones:

- a verdict doesn't record the receipt time it was judged on;
- a promote or acknowledge doesn't record which run's results it relied on;
- a person's decision doesn't record what they were shown, or a GitHub
  comment's text;
- a check's definition isn't pinned to each result;
- the column types the loader inferred are not kept;
- value distributions are recorded for one column per collection only.

The low ones: assumed time zones carry no marker, some instants keep no
local time, and a few defaults claim facts.

**Wider distributions may be the exception** (Keith): recording more
distributions is a gap that could be accepted and filled later by a
targeted regenerate of one dataset, rather than captured now.

## When this comes back

Expected order: pick the tool; scope the migration requirement (amending
REQ-PIPE-144 and the other requirements that say "regenerate, never
migrate"); adopt or amend the five rules; then decide which rule-3 gaps to
capture before the first real deployment. The supply-row samples move and
the file-home question have answers already and can be scoped with it.
