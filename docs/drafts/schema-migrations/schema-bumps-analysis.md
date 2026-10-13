<!-- Read-only analysis of the 38 qa schema version bumps, for Keith's #89 question (2026-10-14): could each have been migrated in place, and would it have needed QA re-run in production? -->

# qa schema bumps: could each one have been migrated in place on a real asset?

Source: `git log --reverse -G"^SCHEMA_VERSION = " -- qa_tools/common/qa_store.py`. That gives
38 commits covering versions 2 to 40. Every diff of `qa_store.py` was read, along with the
commit messages where a change's purpose was not obvious. The requirements read were
REQ-PIPE-168, REQ-PIPE-144 c28-30 and c40, and REQ-PIPE-089 (taken from the DDL comments and
the commit messages).

**Before the history starts.** Version 1 is implicit. The schema was created without a version
in f062e22 (2026-09-26) and executed for the first time in c19da2b (2026-09-27), which also
made unversioned DDL edits. `SCHEMA_VERSION` and `qa.schema_version` first appear in 93f5ada.
No version 16 was ever committed: 83b3442 goes straight from 15 to 17.

**DDL changes made without a bump.** I scanned every other commit to `qa_store.py`. Only one
DDL edit shipped without a bump: 99abafd (2026-10-04) relaxed `decision_supersede_shape`.
e09390f is the bump that delivered that change to existing databases, and its own diff is a
comment only.

**What the project actually did.** Versions 2 to 17 were brought forward with idempotent
"self-healing" DDL: `ADD COLUMN IF NOT EXISTS`, plus constraints that are named and then
dropped and re-added. Version 18 (REQ-PIPE-144) added `RESHAPED_AT = 18`, which refuses any
database older than 18. Versions 19 to 23 were still applied additively in place. Version 24
(8a942e7, Keith, 2026-10-05) changed the rule to "every older version is refused - regenerate,
never migrate".

Category key: (a) additive only; (b) SQL backfill from qa rows; (c) needs a recompute from
supply rows, delivery or receipt files, or tool output not held in qa; (d) needs the QA tools
re-run; (e) a hand-written data move or reshape; (f) a tightened constraint or trigger that
existing rows might violate; (g) a semantic change, which needs a marker or a cut-over.

## Per-bump table

| # | ver | date | commit | what changed | cat | in place? | QA re-run? | risk |
|---|---|---|---|---|---|---|---|---|
| 1 | 1->2 | 09-27 | 93f5ada | New `qa.schema_version`. `run.run_by`, `run.environment` and `check_result.check_name` get DROP NOT NULL. New `qa.load_outcome` (bigserial id, `recorded_at` as text, `trial_run_id`) plus 3 indexes. agency, collection and tool now come from the invocation rather than the record (write path only). The load log moves off disk. | a + e | yes, plus a one-off import of the on-disk load log | no | The import must insert rows in the ORIGINAL append order, because "latest" is now `id`. Sorting by the `recorded_at` string is the bug this change fixed. Don't import trial records. |
| 2 | 2->3 | 09-27 | 91eb824 | New `qa.delivery` (`received_at` text plus `received_instant`, collections/held/anomalies jsonb) and `qa.delivery_file`, with indexes. `ADD COLUMN IF NOT EXISTS trial_run_id` repairs v2's gap. The committed `delivery_log/` tree moves into these tables. | a + e | yes, plus an import of the committed delivery log | no | `recorded_at DEFAULT now()` would stamp every imported row with the migration time, so set it explicitly or document it. Keep `received_at` text verbatim (its offset is protected by REQ-PIPE-069 c5). |
| 3 | 3->4 | 09-27 | 387b0d6 | `run.run_timestamp` changes from timestamptz to text, with a new `run_instant timestamptz NOT NULL` and a `run_when` index. New publisher role with read-only access to `qa`. Same phase as the move of the `qa_results/` tree into `check_result`. | b + c | only with a recompute for the offset | no | **Silent history change.** The v2 column stored only an instant, so the offset each run was recorded on is already gone. `ALTER ... TYPE text USING run_timestamp::text` would write the server session's offset (`+00:00` for `+08:00`), which is exactly the bug this change fixed. `run_instant` is a clean SQL copy. The original text has to come from the `qa_results/` JSON, or be derived from the asset timezone in config. A real asset would also have needed the `qa_results/` import that Keith chose not to build (REQ-PIPE-089 c25, `qa_results_migrate.py` deleted). |
| 4 | 4->5 | 09-27 | 93a637c | New `qa.decision` (action CHECK, slot pair, actor and actor_kind, reason, `effective_at`/`recorded_at`) with 2 indexes and append-only triggers (UPDATE/DELETE and TRUNCATE). The publisher role has write explicitly revoked. Replaces the committed decision-log files. | e | yes: import the files BEFORE creating the triggers | no | Import `recorded_at` from the files, not `now()`. Once the triggers exist, every later fix-up of this table needs them bypassed, which matters for #24, #25 and #29. |
| 5 | 5->6 | 09-27 | a388a13 | New `qa.filing` (slot nullable, branch, `record` jsonb, PK (dataset, supply)) with 2 indexes. `REVOKE ALL ON SCHEMA public FROM PUBLIC`. | a (+g) | yes | no | Filing recording had been switched off, so there is no history to move. The temptation would be to backfill filings by re-running the assignment rule. REQ-PIPE-104 c2 forbids that: a filing is never re-derived against a schedule that has since moved on. Older supplies have to stay unfiled. |
| 6 | 6->7 | 09-27 | 4848125 | `delivery.received_from text NOT NULL DEFAULT 'our-clock'`. | a | yes | no | None. The default is deliberately the WEAKER claim, so old rows don't assert that storage stamped them. This is the model for a default on history. |
| 7 | 7->8 | 09-28 | 8c52cc4 | `substitute` and `de-substitute` actions, `decision.stands_on`, named shape constraints, `decision_stands_on` index. | a | yes | no | The constraints only touch new actions. ADD CONSTRAINT validates existing rows without firing the UPDATE trigger. |
| 8 | 8->9 | 09-28 | 0f9cfda | `inherit` and `inherit-refused` actions. The inline action CHECK is dropped and replaced by a named one (the generated name had stopped an older database picking up the new list). `decision.supply` DROP NOT NULL plus a CHECK. New `qa.period` (opened_by, opened_at). | a + b | yes, with a backfill of `qa.period` | no | Existing period schemas have no period row. Inheritance happens "once, when a period is opened", so a missing row could make the next pass treat an old period as newly opened and write NEW inherit decisions. A backfill (`opened_at` from the first decision into the period) is an inference, while c3 asks for a fact. Mark it, for example `opened_by='migration-inferred'`. |
| 9 | 9->10 | 09-28 | d105f8e | `un-inherit` action plus shape. | a | yes | no | none |
| 10 | 10->11 | 09-29 | 2b90b12 | New `qa.hold` (kind, reason jsonb, `raised_by` NOT NULL, resolved_by FK to decision, resolved_at) plus a partial index. Before this, holds lived only in a run's memory. | b + g | yes, with a partial backfill | no | Assignment-rule holds can be recovered from `filing` rows where `slot IS NULL`, and delivery-level holds from `delivery.held`. Whether each hold was since resolved has to be matched against the decision log. `raised_by` is NOT NULL and placeholders are forbidden, but no run raised these holds. That needs a marker, or relaxing NOT NULL for history. |
| 11 | 11->12 | 09-30 | 7c22aaa | `promotion-withheld` action plus shape. | a | yes | no | The RULE changed: mixed-period deliveries are no longer auto-promoted. Earlier auto-promotions stay as recorded facts, which is correct. Don't "fix" them. |
| 12 | 12->13 | 10-02 | 2e3cfaf | `filing.received_at timestamptz` and `filing.classification` (the lateness verdict). | b + g | yes | no tool run, but filling it means re-judging | `received_at` is an SQL backfill from `qa.delivery`. `classification` is a VERDICT computed from the receipt and the calendar config. Backfilling it judges history with today's calendar, which REQ-PIPE-168 forbids (verdicts are recorded facts, with their inputs). Leave it NULL ("not recorded at the time"). |
| 13 | 13->14 | 10-03 | 17e983e | Renames `delivery.held` to `contested` (a guarded DO block). | e (trivial) | yes | no | none |
| 14 | 14->15 | 10-04 | 73e829b | New function `qa.slot_holds(dataset, as_at)` and view `slot_holds_now`. Replaces five Python readers. | a | yes | no | This is a derived reading, so answers about history change wherever the old readers were wrong (#75/#84/#85). That is correct. Anything the old readers already stored stays as recorded. |
| 15 | 15->17 | 10-04 | 83b3442 | DROP and CREATE `slot_holds` with new `held_as` and `holder` columns. The excluded-refusals list becomes an allow-list. Fixes a NULL comparison. | a | yes | no | DROP and CREATE must run in dependency order: view first, then function. |
| 16 | 17->18 | 10-04 | 6f90090 | **REQ-PIPE-144 reshape.** `delivery.contested` dropped (now the `delivery_contested` view). `delivery_file` gains `received_at`, `received_instant`, `received_from` and `receipt_sequence`, all NOT NULL: per-file receipts that used to live in `data/receipts/`. `filing.record jsonb` dropped and replaced by `considered text[]`. New `filing.delivery NOT NULL` FK to delivery. `filing.received_at` dropped (now the `supply_receipt` view). `delete_history()` removed. `RESHAPED_AT`, and older versions refused. | e + c + f | yes, but only with a hand-written migration, and only if every file has a receipt | no | **The biggest loss point.** (1) The receipt facts come from receipt FILES, not from qa, and NOT NULL fails on any file without one. (2) Dropping `record` loses fields: the "ambiguity mark" was retired. Archive the jsonb rather than drop it. (3) Before dropping `filing.received_at`, assert it equals `supply_receipt.received_instant`. Supplies from before REQ-PIPE-105 had one receipt per delivery, and if the per-file value differs, the basis of every lateness verdict silently moves. (4) Assert that `contested` equals the new view before dropping it. |
| 17 | 18->19 | 10-04 | e01c1fd | `delivery.filed_by_kind NOT NULL DEFAULT 'automated'`, `filing_route`, `filed_by` plus a shape CHECK. `delivery_file.originally_received_stated`. | g | yes structurally, but the default lies | no | The default makes every historical delivery, hand-filed ones included, claim `automated`. REQ-PIPE-147 c1 forbids inferring from the `handfiled-` name, so the only honest backfill is "not recorded", and the CHECK has no such value. Compare #6, which got this right. |
| 18 | 19->20 | 10-04 | 0f96148 | `mark-not-supplied` action plus shape. `supply_present` extended. | a | yes | no | none |
| 19 | 20->21 | 10-04 | 1798c63 | `acknowledge` action. `amber_setting`, `amber_level`, `amber_version`. A generated STORED column `acknowledgement_owed`. Constraints. | a | yes | no | NULL is honest for history, because no setting existed. Adding the STORED column rewrites the table under an exclusive lock, but that is not an UPDATE, so the append-only trigger doesn't fire. Don't backfill the amber setting from today's config. |
| 20 | 21->22 | 10-04 | 5063641 | `supersede` and `un-supersede` actions, `decision.superseded_by`, shape. | a | yes | no | none |
| 21 | 22->23 | 10-04 | e09390f | **This commit only bumps the number.** The DDL (a relaxed `decision_supersede_shape` for a person's supersession) shipped earlier in 99abafd with no bump, so a database already at 22 kept refusing it. | a | yes | no | This shows the weakness of a version-gated, idempotent script: an edit that isn't bumped never reaches an existing database. |
| 22 | 23->24 | 10-05 | 8a942e7 | `delivery_file.originally_received_stated_instant`. Policy change: every older version is now refused. | b | yes, with an SQL backfill (parse the text column, `not-known` becomes NULL) | no | Parse using the stated offset, not the session timezone. |
| 23 | 24->25 | 10-05 | 7bc7b1a | `tables_read.supply`. New `qa.census` and `census_discrepancy`. The period-table guard event triggers are installed with the schema. **Outside qa, period tables are renamed from stamped names to plain base names (REQ-PIPE-129).** | b + e | yes, with a backfill plus a warehouse rename | no | `tables_read.supply` can be backfilled from `slot_holds(dataset, run_instant)`. The warehouse rename removes the supply identity from the table name, so record it first. Old `tables_read.physical_table` values name tables that no longer exist. The guard must be installed AFTER the rename, or it refuses the rename. |
| 24 | 25->26 | 10-05 | 11eb18e | `run` gains `dataset_id`, `supply_id`, `scope NOT NULL DEFAULT 'arrival'`, `period`, `reads_table`, `caused_by_*` and CHECKs. `filing` PK changes from (dataset, supply) to `id bigserial`, with a `refiled_by` column, a `filing_once` partial unique index and an append-only trigger. New `filing_current` and `supply_current_run` views. New `qa.owed_run`. **`slot_holds`: a re-file no longer fills the slot it goes to.** | e + b + g | structurally yes; honestly only with a marker or cut-over | no | **The most dangerous bump.** (1) Before this, a `refile` moved the supply INTO `to_slot` as promoted. The new view reads the same historical rows as leaving that slot empty, so past periods' contents change and nothing errors. The fix is a new action name, or a semantic-version column on decision; reinterpreting the old one is wrong. (2) Before v26, a re-file UPDATED the filing row (a388a13's comment says so), so the rule's original filing is already lost. The surviving row would get `refiled_by IS NULL`, meaning "the rule's own filing", which is false. It can be partly repaired from the decision log's refile entries. (3) `run.supply_id` can only be backfilled by parsing the run id, which is the inference this requirement replaced. Mark it as inferred. |
| 25 | 26->27 | 10-05 | 8040a69 | `still-failing` action. `decision.table_name`, `promoted_status`, `replaces`, `replacement_setting`, `replacement_level`, `replacement_version`, `caused_by_decision` plus constraints. New SECURITY DEFINER function `manifest_for()`. | b + g | yes, with a backfill, but every backfill is an UPDATE on an append-only table | no tool run; `promoted_status` would be re-derived | `table_name` comes from contract config, and `replaces` from `slot_holds` as at `effective_at`. Both are mechanical. `promoted_status` must be "fixed when taken, never looked up later". A backfill would recompute it from recorded results with TODAY's status-rollup code, which has changed (for example nullable thresholds, item 74). Leave it NULL. `replacement_*` should be NULL, because no setting existed. Every UPDATE needs the append-only trigger bypassed inside the migration. |
| 26 | 27->28 | 10-05 | 8fb2229 | `manifest_for` search_path gains `pg_temp` (security fix). | a | yes | no | none |
| 27 | 28->29 | 10-05 | 4305585 | `check_result.load_attempt`, `delivery`, `filename`. New `_file` scope. A new "file" check tool runs before each file is loaded. | a (+d) | yes | **Only to fill history, and it should not be run.** Running it would create NEW verdicts for old files under today's checks. | History has no file-check results. The dashboard must say "not file-checked (predates)", never "passed". Recorded verdicts are unchanged either way, because this adds verdicts rather than altering any. |
| 28 | 29->30 | 10-05 | 827636e | The anonymous inline `decision_check` is replaced by a named `decision_names_a_slot` that allows `promotion-refused`. New action. | a | yes | no | Only relaxes a constraint. |
| 29 | 30->31 | 10-06 | a17d6e8 | `decision.caused_by_supply` plus shape. `supply_current_run` reordered onto the asset timeline (DROP and CREATE). | a | yes | no | Backfilling `caused_by_supply` would use the time-window heuristic Keith rejected, so leave it NULL. The view change can name a different "current run" (and so a different current verdict) for some historical supplies. It is a fix, but say so. |
| 30 | 31->32 | 10-06 | 5c5a616 | `supply_current_run` tie-break on `run_instant`. | a | yes | no | Same note as #29. |
| 31 | 32->33 | 10-06 | 5608936 | `delivery_file.storage_uri`. | b | yes, with an SQL backfill (`'local:'||delivery||'/'||filename`) | no | Check that each file exists on disk. |
| 32 | 33->34 | 10-10 | 51df202 | New append-only `qa.verdict` (filing_id, classification, inputs jsonb, fingerprint, correction refs, supersedes). `filing_current` takes its classification from the newest verdict. | b | yes, with a backfill: INSERT one first verdict per filing from `filing.classification` (an insert, which append-only allows) | no | `inputs` and `fingerprint` must be NULL for history. Recomputing them from today's calendar would fabricate the agreement that judged the verdict, and the REQ-PIPE-173 backstop would then compare against fiction. |
| 33 | 34->35 | 10-10 | d6dce26 | Verdict CHECKs (non-empty correction refs). Unique partial indexes `verdict_first_once` and `verdict_supersedes_once`. `verdict_matches_filing` trigger. `excuse-lateness` and `withdraw-excuse` actions. | f | yes, if no rows violate | no | The CHECKs were added inside `CREATE TABLE IF NOT EXISTS`, so the project's own script would never have applied them to an existing table. An explicit ALTER would, and could fail on duplicate or empty rows that the append-only rule then won't let you fix. |
| 34 | 35->36 | 10-10 | 0d3af2e | New append-only `qa.correction_applied`. `keep` action. `slot_holds` refile fix (`IS NOT DISTINCT FROM`). | a | yes | no | none |
| 35 | 36->37 | 10-11 | 1af4eff | New `qa.correction_parked` and `correction_parked_resolved`, both append-only. | a | yes | no | none |
| 36 | 37->38 | 10-12 | d11ac27 | New `qa.asked_check` (what each tool was asked to evaluate). | a | yes | no | It is designed so that no rows means "not recorded". Don't backfill from the config of the day. |
| 37 | 38->39 | 10-12 | 67339d9 | New parent `qa.asked_tool`. `asked_check` gets a composite FK to it. | e (SQL) | yes, with a backfill (`INSERT asked_tool SELECT DISTINCT run_key, tool FROM asked_check`, then add the FK) | no | v38 runs with an empty ask left no row, so they read as "not recorded". The gap is small and honest. |
| 38 | 39->40 | 10-13 | 128f6a1 | `choose-file` action plus shape. New append-only `qa.decision_file`. The `supply_receipt` view prefers the settled file. | a | yes | no | With no settlements in history, the view falls back to the earlier-file rule and gives the same answers. This assumes supply-id naming did not change in code at the same time; I didn't verify that. |

## Summary

**Counts, one primary category per bump (38 bumps):**

| category | count | versions (to) |
|---|---|---|
| (a) additive | 19 | 6, 7, 8, 10, 12, 15, 17, 20, 21, 22, 23, 28, 30, 31, 32, 36, 37, 38, 40 |
| (b) SQL backfill from qa | 5 | 9, 24, 33, 34, 39 (plus parts of 4, 11, 13, 25, 26, 27) |
| (c) recompute from files or data outside qa | 1 | 4 (the run offset; 18's receipts are also partly c) |
| (d) needs the tools re-run | 1 | 29 (file checks, and only to fill history) |
| (e) hand-written data move or reshape | 6 | 2, 3, 5, 14, 18, 25 |
| (f) constraint tightening | 1 | 35 |
| (g) semantic change | 5 | 11, 13, 19, 26, 27 |

**In place?** Every bump could have been applied in place on a real database. None is a hard
"no". About 19 are trivially safe. About 13 need a backfill or a data move: SQL-only in most
cases, and file imports at 2, 3, 5 and 18. Version 4 needs the original offsets recovered from
outside qa. The 5 (g) bumps are "in place structurally, but honest only with a marker or a
cut-over". The worst is v26, where a re-file stopped filling its target slot.

**QA re-run in production:** 0 bumps genuinely needed the tools re-run. Only v29 (file checks)
would need one, and only to fill history; it should not be run, because it would add
present-day verdicts about old files. If the backfill rules below are followed, no recorded
verdict changes. The real temptation was never the tools. It was RE-JUDGING: recomputing a
verdict-like value from recorded data with today's code or config. That applies to v13
`classification`, v27 `promoted_status`, the v34 verdict `inputs` and fingerprint, v11 hold
provenance and v31 `caused_by_supply`. None of these needs dbt, Soda, datacontract-cli or
Evidently, and all of them would silently re-judge history.

**Patterns.**
- **Safe:** new tables, new nullable columns whose NULL means "not recorded", new indexes, new
  actions added to a CHECK, relaxed constraints, and derived views and functions. A view change
  alters answers about history, but it doesn't alter the facts.
- **Dangerous (silent loss or change):**
  - a default that asserts a fact (v19 `automated`);
  - a type change that drops information (v4 timestamptz loses the offset);
  - dropping a stored copy in favour of a derivation without proving they agree (v18 receipts,
    `contested`);
  - dropping a jsonb document (v18 `record`);
  - changing how an existing append-only action is READ (v26 refile);
  - UPDATE-in-place history that was later made append-only (the v26 filings had already been
    overwritten);
  - any backfill that has to UPDATE an append-only table (v25 through v27);
  - constraints written only inside `CREATE TABLE IF NOT EXISTS` (v9, v23 and v35 show the real
    misses).

**Design rules that would have made the dangerous ones safe:**
1. **NULL means "not recorded at the time", never a default that claims a fact.** A default on
   history must be the weakest true claim (v7's `our-clock`), or nothing at all (fixes v19,
   v27 and v31).
2. **A verdict-like or config-derived value is never recomputed for history.** It is NULL, or
   a NEW appended row that names the code and config version that computed it (the
   `qa.verdict` pattern). This fixes v13, v27 and v34.
3. **Record raw evidence at the time, and keep text alongside instants.** Then a new derived
   column is an SQL backfill rather than a recompute. The receipt text and offset, the raw tool
   output already kept in `tool_output`, and the run offset would all have been safe. v4's loss
   came from storing only an instant.
4. **Version the meaning of append-only facts.** When an action's semantics change, add a new
   action (or a semantic version on the row) instead of re-reading old rows under the new rule.
   This fixes v26's refile.
5. **Reshape by expand, verify, contract.** Add the new columns, backfill, ASSERT the old and new
   values agree, archive (rather than drop) any document, and only then drop. Give migrations
   one audited bypass for append-only triggers (DISABLE TRIGGER inside the migration's own
   transaction, logged to a migration-audit table), never an app-side UPDATE. This fixes v18
   and v25 through v27.

**Does Alembic, Django or a hand-rolled runner change any of these answers?** No. Every answer
above depends on what information exists, not on the migration tool. What a real migration tool
changes is mechanics, and those mechanics caused real bugs here. Ordered, explicit
per-revision steps replace the idempotent "self-healing" script, which:
- silently skipped column and constraint changes inside `CREATE TABLE IF NOT EXISTS` (v3,
  v9, v35);
- silently skipped an unbumped edit (99abafd, then v23).

Neither tool would help much with this schema's real content:
- **Alembic** autogenerate on its own doesn't see triggers, functions or views; with the
  alembic_utils extension (0.8.8) it does generate functions, views, triggers and policies
  (CORRECTED by the main session, 2026-10-14, from the extension's own README). Event
  triggers and every data-moving reshape stay hand-written either way.
- **Django** would be `RunSQL`/`RunPython` around raw SQL. It also needs ORM models and a Django
  app, which this project doesn't have.

Either tool also replaces "every writer self-migrates under an advisory lock" with an explicit
deploy step. That reverses a recorded decision (`ensure_schema`: "a pipeline that only works
after somebody remembered to run a migration is a pipeline that fails on a new environment").
That decision would need to be re-opened with Keith, not assumed away. Given the raw-SQL nature
of the schema, a small hand-rolled runner (numbered SQL and Python files plus the existing
version table and advisory lock) would be as good as Alembic, and lighter than Django.
