# REQ-QAC-247 criterion 1: one brief per behavioural legacy flag

Drafted 2026-10-18 for Keith. All figures come from read-only SELECTs against
`$MOTHMAN_SUPPLY_DSN` (schema `qa`, plus a read-only look at the promoted,
staged and rejected Birth Registrations tables for one brief) or from the code
named. Nothing was written, run or regenerated.

**The recorded history these figures describe:** Birth Registrations (BR) has
118 runs. 111 of them ran all four tools; the other 7 are the contested
two-file deliveries, where the run's own table could not be read, so they hold
only the 12 file checks each. Child Protection (CP) has 364 runs. Every legacy
flag is declared by BR's adapter. CP's adapter declares none.

**Why most of these change nothing today.** BR has one table, and the
orchestrator never runs a tool when a run's own table cannot be read. So every
BR tool run so far has had its only table readable, and every flag that covers
"a table this run cannot read" is unreachable for BR. 13 of the 16 flags change
nothing in today's history. Three flags change something, and so does the
non-flag item (CP's empty dimensions).

---

## 1. datacontract.reads_unreadable_tables

**What differs.** For CP, datacontract-cli drops any rule over a table the run
cannot read and notes it as "left out", so the run can reconcile it with its
could-not-run records. BR's copy never had this handling: it records every
rule it gets back and notes nothing.

**Worked example.** CP run `cp_clients__202108010100000000` left out 4
datacontract rules, e.g. `...cp-investigations.cp_client_id.relationships_datacontract`.
CP has 36 runs with a left-out record, with 88 rules left out per tool across
them. **For BR the flag changes nothing:** 0 of 111 BR tool runs had an
unreadable table, and none could, as explained above. It would only show if BR
gained a second table, or if the own-table guard were bypassed.

**Proposals.**
- A. Unify on CP's behaviour. 0 recorded BR results change, and BR runs start
  noting what they leave out (none so far).
- B. Keep it as a BR setting. That keeps a code path BR cannot reach.

**Recommendation.** Option A, because it changes nothing on record and removes a
branch that can never run.

## 2. soda.reads_unreadable_tables

**What differs.** As in brief 1, for Soda. CP removes checks over unreadable
tables before the scan and notes them as left out. BR hands Soda every check
and notes nothing.

**Worked example.** The same CP run `cp_clients__202108010100000000` left out 4
Soda checks, e.g. `...cp-investigations.cp_client_id.relationships_soda`.
**For BR it changes nothing**, for the same reason as brief 1. No BR Soda
result carries a not-evaluated reason (0 records).

**Proposals.** A. Unify on CP's behaviour: 0 changed results. B. Keep it as a
setting.

**Recommendation.** Option A, for the same reason as brief 1.

## 3. evidently.reads_unreadable_tables

**What differs.** CP evaluates its drift (PSI) check only when the run can read
its table, and notes it as left out otherwise. BR always evaluates it.

**Worked example.** **It changes nothing in either collection's history.** BR's
drift check is on `birth_registrations.sex`, which was readable in all 111 BR
tool runs. CP's 36 left-out records name dbt, Soda and datacontract-cli only.
None names Evidently.

**Proposals.** A. Unify on CP's behaviour: 0 changed results. B. Keep it as a
setting.

**Recommendation.** Option A.

## 4. dbt.no_left_out_note

**What differs.** Both collections exclude dbt models over unreadable tables.
CP also notes the tests it excluded as left out. BR excludes them but notes
nothing.

**Worked example.** CP run `cp_clients__202108010100000000` noted 4 dbt tests,
e.g. `...cp-investigations.cp_client_id.relationships_dbt`. **For BR it
changes nothing, and cannot.** When BR's one table is unreadable, dbt has
nothing left to build, and the code returns before it reaches the note
(`run_dbt.py`, `NothingLeftToBuild`).

**Proposals.** A. Unify on CP's behaviour: 0 changed results. B. Keep it as a
setting.

**Recommendation.** Option A. This branch is unreachable for any one-table
collection.

## 5. dbt.no_built_model_guard

**What differs.** CP counts the table's rows, recounts a test's audit table
and samples failing rows only if dbt actually built the model. BR does all
three regardless.

**Worked example.** **It changes nothing.** dbt's own results show the model
built successfully in all 111 BR dbt runs (111 model nodes, all `success`).
No BR dbt result has an empty `row_count_total` (0 of 2,775). The flag would
only show if `stg_birth_registrations` failed to build while its tests still
ran.

**Proposals.** A. Unify on CP's behaviour: 0 changed results. B. Keep it as a
setting.

**Recommendation.** Option A. Counting a model that was not built can only give
a wrong number or an error.

## 6. dbt.audits_skipped_tests

**What differs.** For a dbt test reported as skipped, CP does not recount it
from its audit table, and keeps dbt's own skip. BR still recounts it, so a
skipped test can come back with a pass or fail worked out from that table.

**Worked example.** **It changes nothing.** dbt's own results across both
collections show no skipped or errored test at all. The statuses recorded are
pass, warn, fail and (for models) success. The flag would only show if an
upstream node failed and dbt skipped the tests that depend on it.

**Proposals.** A. Unify on CP's behaviour: 0 changed results. B. Keep it as a
setting.

**Recommendation.** Option A. Whether a skipped test's audit table holds
current rows is not verified, so a verdict worked out from it should not be
trusted.

## 7. soda.scope_suffix  (reader-visible in the results file, not on the page)

**What differs.** BR records each generically named Soda check as
`<metric>[<filter or all>]`, for example `invalid_percent[all]`. CP records it
as plain `<metric>`, for example `invalid_percent`. In practice the suffix is
always `[all]`: BR's one filtered check has its own custom name.

**Worked example.** Run `birth_registrations__20260713062345582172`, check
`...birth-registrations.child_given_names.invalid_percent_soda` is recorded as
`check_name = invalid_percent[all]`, 2.12, warn. The CP equivalent is recorded
as `invalid_percent`. **The page does not show this name.** BR's card reads
"Invalid values" (the label), and the dashboard identifies a check by its
check id, not by this name. Two code paths do read the suffixed name:
- BR's adapter attaches the sex and suburb aggregates to `invalid_percent[all]`.
- `_SUPPLY_LEVEL_CHECK_NAMES` lists both spellings of the row-count check.

**Proposals.**
- A. Unify on CP's plain name. 20 BR checks and 2,220 recorded results change
  name; no status, value or dimension changes. The adapter's two aggregate
  names must change in the same change, or the sex and suburb Soda cards lose
  their aggregate figures.
- B. Unify on the suffix. 48 CP checks and 2,758 results gain `[all]`.
- C. Keep it as a BR setting.

**Recommendation.** Option A. The suffix carries no information today, and
dropping it makes one name per metric across collections.

## 8. soda.named_check_value_is_invalid_count

**What differs.** For a custom-named Soda check routed to a column, BR records
the check's own value as the count of invalid rows when nothing else supplies
that count. CP leaves the count empty.

**Worked example.** **It changes nothing.** BR's 5 routed checks never reach
this branch:
- The "fail query" checks always carry a Soda "Failed Rows" block, even when
  they pass, so the block branch runs first.
- The "fail condition" checks read Soda's `row_count` metric, so they get 0.

The flag would only show for a custom-named metric check, such as a named
`missing_count`, listed in `column_by_name`.

**Something else found while checking this, which is not this flag.** In both
collections, a failing failed-rows check records an empty invalid-row count.
The code reads `totalFailingRows`, but Soda's block carries `totalRowCount`.
Run `birth_registrations__20260702064846982691`, "date_of_birth is within a
plausible range": value 24, Soda's block says `totalRowCount: 24`, recorded
`row_count_invalid` is empty. This happens in 50 BR fail results, and in 3 fail
and 1 warn for CP's "date_of_birth out of range". It looks like a defect to
write up separately, test first.

**Proposals.** A. Unify on CP's behaviour: 0 changed results. B. Keep it as a
setting.

**Recommendation.** Option A, and log the empty-count finding in
post-build-review.

## 9. stats.zero_counts_kept

**What differs.** In a value-count distribution, BR lists every known value,
zeros included. CP lists only the values that occur. The page shows these
counts (`valueCounts` on the sex column).

**Worked example.** **It changes nothing.** None of BR's 118 stats records has
a zero for sex: M, F and X are always present. None of CP's 343
`concern_type` records is missing a known value.

**An overlap to settle first.** REQ-PIPE-248 criterion 1, already signed off,
says "zero counts treated as Child Protection treats them". So this flag is
claimed by both requirements. It is also visible to a reader in principle: a
category that drops to zero would vanish from the chart. That sits badly with
REQ-PIPE-248's "invisible to a reader" rule.

**Proposals.**
- A. CP's behaviour, as REQ-PIPE-248 already says: 0 changed results.
- B. Keep zeros for every collection: 0 changed results today. A future zero
  becomes a visible bar rather than a missing one.

**Recommendation.** Option B. "Neglect: 0" tells a reader more than a missing
row does. Either way, decide which requirement owns this flag.

## 10. stats.arrival_after_registration  (changes recorded values; nothing reads them)

**What differs.** For a supply's recorded `earliest_extract`, BR takes the
earliest timestamp among rows extracted on or after their registration date.
CP takes the plain earliest. CP's tables have no `date_registered`, so BR's
rule cannot apply to CP as it stands.

**Worked example.** Run `birth_registrations__20260713062345582172` recorded
`earliest_extract = 2026-07-13T06:23:45`. 43 of its rows were extracted before
their registration date, the earliest at 2026-07-12 20:00, which CP's rule
would record instead. Checked against the 117 BR supply tables that still
exist: **18 supplies' recorded value would change.** **No dashboard reader
uses it.** It appears only in `reports/results_bdm.json`. `pipeline/recorded_arrival.py`
records that receipt time replaced it for punctuality.

**Proposals.**
- A. CP's plain earliest: 18 recorded values change, nothing on the page.
- B. Stop recording `earliest_extract`. No product code reads it (grep only;
  an outside reader is not verified).
- C. Keep it as a BR setting.

**Recommendation.** Option B, because a figure nobody reads is not worth
unifying. Fall back to A if anything needs it.

## 11. results.every_recorded_run

**What differs.** When the results file is rebuilt from history, BR reads
every recorded run, including runs a newer run of the same supply has
replaced. CP reads only each supply's current run.

**Worked example.** **It changes nothing.** BR has 6 replaced runs, e.g.
`birth_registrations__202607281340000800`, but each holds only the 12 file-check
results (72 in all), and this path does not read those. All 8,880 four-tool BR
results sit on current runs, and the results file holds exactly 8,880. The
flag would show as soon as a BR supply is re-checked: the older run's results
would then be in the file.

**Proposals.** A. Unify on CP's behaviour: 0 changed results. B. Keep it as a
setting.

**Recommendation.** Option A. The rule that the dashboard shows a supply by its
current run (REQ-PIPE-140) should hold for every collection.

## 12. orchestrate.single_table_guard

**What differs.** Before running the tools, the orchestrator checks the run's
own table is readable. BR always guards its one table. CP guards the table the
run id names, and a run whose id names no table (a trial or a fixture) is not
guarded.

**Worked example.** **It changes nothing.** All 118 BR run ids name
`birth_registrations`, so both rules guard the same table. The guard is why 7
BR runs recorded only file checks. The flag would show only for a BR trial or
fixture run.

**Proposals.** A. Unify on CP's behaviour: 0 changed results. B. Keep it as a
setting.

**Recommendation.** Option A.

## 13. orchestrate.files_one_arrival

**What differs.** CP files an arrival together with every other arrival that
shares its exact receipt time, following Keith's 2026-10-03 rule that a zip is
filed whole. BR files each arrival alone.

**Worked example.** **It changes nothing.** All 118 BR files have distinct
receipt times. The 7 two-file deliveries are 5 minutes to about 3 hours apart,
e.g. `REG_20260807`: 05:40 and 08:30. The flag would show for two BR files
received at the same instant, as from one zip.

**Proposals.** A. Unify on CP's behaviour: 0 changed results. B. Keep it as a
setting.

**Recommendation.** Option A. It is Keith's own rule, and BR's exemption is an
accident of copied code.

## 14. orchestrate.always_reconciles

**What differs.** At the end of a run, the orchestrator checks that what the
tools left out matches what was recorded as could-not-run. BR does this on
every run. CP excuses a run whose supply was filed to no period (Keith,
2026-10-12): such a run records no could-not-run records, so there is nothing
to reconcile against.

**Worked example.** **It changes nothing.** All 118 BR runs have a period and
name their table. CP's 8 period-less runs, e.g.
`cp_case_workers__202305010900000800`, never reached the tools: they hold only
6 file checks each. So the excuse has not been used either. The flag would show
for a BR supply filed to no period.

**Proposals.** A. Unify on CP's behaviour: 0 changed results. B. Unify on BR's
behaviour: also 0 today, but a run with no period that left something out
would then be refused.

**Recommendation.** Option A. It matches Keith's 2026-10-12 decision.

## 15. dashboard.drops_empty_sections  (reader-visible on the page; no recorded result changes)

**What differs.** When a section has no checks, CP's page still shows it, with a
grey "No automated quality rule defined" card. BR's page leaves the section out.

**Worked example.** From today's built dashboard files:
- BR shows its 13 columns and "Supply-level checks". "Table-level checks" and
  "Cross-table checks" do not appear at all.
- Each of CP's 6 datasets shows a grey Table-level card. Each also has real
  cross-table checks.

**Proposals.**
- A. Unify on CP's behaviour: BR's page gains 2 grey cards (Table-level and
  Cross-table).
- B. Unify on BR's behaviour: CP's 6 grey Table-level cards disappear.
- C. New: always show an empty Table-level section; show Cross-table only for
  a collection with more than one table. BR gains 1 grey card, and CP's page
  is unchanged.

**Recommendation.** Option C. A missing rule should be visible, as Keith ruled
for CP's grey cards, but a one-table collection has no cross-table gap to
report.

## 16. dashboard.reference_reason_fallback

**What differs.** This flag covers when a card's run is marked "not evaluated".
CP takes the reason from any could-not-run record (unrunnable, held, Soda
could-not-evaluate, or an Evidently "no reference owed" red), and puts real
results before could-not-run records. BR uses only Soda's reason, or a
reference reason on a red with no value, and keeps records in the order they
were recorded.

**Worked example.** **It changes nothing.** BR has no could-not-run record of
any kind (0 unrunnable, held or not-evaluated). Neither collection has an
Evidently "no reference owed" record. No BR Evidently fail has an empty value.
The flag would show for a BR check with both a real result and a could-not-run
record on one run.

**Proposals.** A. Unify on CP's behaviour: 0 changed results or cards. B. Keep
it as a setting.

**Recommendation.** Option A. CP's version is the complete one, and BR's is a
subset of it.

## 17. Not a flag: CP's Soda checks recorded with an empty dimension

**What differs.** A Soda result's dimension comes from the adapter's maps in
`run_soda.py`: by check name for custom-named checks, otherwise by metric.
BR's map covers every metric it uses. CP's map lists only `reference` and
`row_count`, so its `missing_count`, `invalid_percent` and `duplicate_count`
checks get an empty dimension. CP's referential checks miss out as well: their
Soda-generated name contains no "when", so the code treats them as
custom-named, and the `reference` entry is never used. `end_date is not
earlier than start_date` is not in CP's name map.

**Worked example.** Run `cp_placements__202608010900000800`, check
`...cp-placements.placement_start.missing_count_soda`: dimension `''`, the
same as `...carer_id.relationships_soda` in that run. On the page, all such
cards fall into the "Other" group with no dimension tag. **Count: the
requirement's 88 is not reproduced.** Recorded today, the count is 52 CP checks
and 3,357 results, shown as 59 cards on the page (cross-table checks appear on
both tables). The only 88 in the database is CP's left-out total per tool
(brief 1), which looks unrelated.

**Proposals.**
- A. New: take the dimension from the `category` already written on each
  check in the Soda checks file. Every non-empty dimension recorded today
  matches it: all of BR's and CP's 625. The 52 checks would become
  completeness 27 (1,562 results), conformity 11 (643), consistency 8 (815)
  and uniqueness 6 (337). BR: 0 changes. Both adapters' Soda dimension maps
  could go.
- B. Unify on BR's approach: copy BR's metric map to CP, route reference checks
  by metric, and add `end_date`. The values are the same as A, but the maps
  stay.

**Recommendation.** Option A. The dimension is already written next to each
check, and reading it removes a second copy that drifted.

---

## Flags I treat as SHAPE (REQ-PIPE-248), with one exception

- `stage.stamps_run_columns`
- `stats.single_table_shape`
- `stats.rows_by_run_id`: shape as far as I can tell, but not verified. It
  would change counts only if a run's view ever held rows carrying another
  run's id.
- `results.single_dataset_header`
- `orchestrate.entry_carries_csv_path`
- `dashboard.single_dataset_document`
- `dashboard.supply_section_first`: legacy.py itself says no reader sees it.

**Exception: `evidently.volume_from_drift_frame` is behavioural, not shape.**
It changes how the volume check is worked out (a zero-row reference reads as
no drop, and the count comes from the drift frame). It also changes where the
check appears. BR records `evidently:row_count_growth` on
`registration_number` (111 results), and the page shows "Row count vs. last
promoted supply" under that column. CP records it on `(table)` (337 results),
and the page shows it under "Supply-level checks". It needs a brief under this
requirement.

None of the 16 flags I was given turned out to be shape. `stats.zero_counts_kept`
is claimed by both requirements (brief 9).
