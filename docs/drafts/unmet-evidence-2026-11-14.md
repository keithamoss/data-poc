# Evidence for the 30 criteria deferred to the end-of-run bootstrap

Gathered 2026-11-14 (Perth), read-only. Nothing was run that writes: SELECT
queries against `supply_quarterly` and `supply_daily`, plus reading logs, JUnit
files, built reports and repository files. No pytest, no pipeline command.

## Sources, and what each one is

- **Recorded QA history.** `supply_quarterly` and `supply_daily`, bootstrapped
  from empty on 2026-11-03 at tree **ac523de9**. The quarterly bootstrap started
  03:07:25 UTC, a few seconds after that commit. Logs:
  `scratchpad/boot_quarterly.log` (`real 111m8.525s`, `EXIT=0`) and
  `scratchpad/boot_daily.log` (`real 11m23.900s`, `EXIT=0`). Code changed after
  ac523de9 (post-build-review #316-#321), but the databases were not
  re-bootstrapped, so the recorded rows are what ac523de9's code wrote.
- **Test outcomes.** JUnit files in `scratchpad/chunks_old/5ff97f93/`, tree
  **5ff97f93**, run 2026-11-03 14:19-18:12 UTC: 7,722 tests, 7,718 passed,
  2 skipped, 2 failed. The two failures are
  `test_dashboard_e2e.py::TestTheDataFilesLoadFromDisk::test_the_first_view_answers_within_its_budget_of_navigation`
  (trends 6679/6647/6683 ms against 6000) and
  `test_correction_trial.py::TestTheCalendarEntry::test_the_view_edits_no_configuration`
  (the `dbt/logs/dbt.log` snapshot, fixed in 7c04843a). The e2e module
  (`junit_e2e.xml`, 437 tests, 1812.67s) builds its dashboard from
  `supply_<asset>`, through `tests/conftest.py::deployment_dsn_for`. The newer
  run in `scratchpad/chunks/` (tree a35066ff) had finished only chunks 00-04, and
  none of the results below come from it.
- **Built reports.** `reports/quarterly/*.json` and `reports/daily/*.json`,
  written 2026-11-03 11:06-11:08 UTC from the recorded results.
- **CI.** I have no GitHub access. The caller reports critical runs 41692776303
  and 41696483015 as green, and says no `test.yml` run has been started by hand
  since the build.

**How the verdicts are used here.**
- **MET**: the recorded data or a real test outcome shows what the criterion
  says.
- **NOT MET**: the evidence contradicts the criterion, or an action the
  criterion requires (a measurement recorded, a CI run, a gate run) has not
  happened.
- **CAN'T TELL**: the proof the criterion names has not been run, and nothing
  else available shows the property either way.

All SQL below ran with `psql "postgresql://user:password@localhost:5432/supply_quarterly" -tAc "..."` unless a query says otherwise.

---

## REQ-QAC-333

### [1] Criterion 6, the failing-rows half: the referential check records its failing rows as dataset code and identifier values. **MET**

```sql
select id, run_key, left(extra::text,1500) from qa.check_result
where dataset_id='linkage-keys' and tool='soda'
  and check_id like '%referential_soda' and status='fail';
```
```
6511|linkage_keys__201808011730000800|{"tables_read": {"ed_presentations": "ed_presentations__201808010845000000"}, "failing_sample_keys": [["EDDC_PRESENTATION", "ED60022002529", null]], "failing_sample_key_columns": ["dataset", "id_1", "id_2"]}
10843|linkage_keys__202205011730000800|{"tables_read": {"cp_clients": "cp_clients__202202010100000000"}, "failing_sample_keys": [["DOC_CLIENTS", "CPS-0837638049", null]], "failing_sample_key_columns": ["dataset", "id_1", "id_2"]}
11419|linkage_keys__202211011730000800|{"tables_read": {"cp_clients": "cp_clients__202208010100000000"}, "failing_sample_keys": [["DOC_CLIENTS", null, null]], "failing_sample_key_columns": ["dataset", "id_1", "id_2"]}
```
- These are the same three results that post-build-review #291 found recorded
  with `failing_sample_keys: []`. Each one now names its row by dataset code and
  identifiers, so **the defect does not show in this bootstrap**.
- The third sample has a null `id_1`. That is the row itself, not a dropped
  value. `select dataset,id_1,id_2 from staging.linkage_keys__202211011730000800 where dataset='DOC_CLIENTS' and id_1 is null`
  returns one row, `DOC_CLIENTS||`, the only null `id_1` in the table. Per
  REQ-PIPE-341, a null part is kept as null.
- **The other halves of criterion 6 hold too.**
  - Every referential result carries `tables_read`: fail 3 of 3, pass 91 of 91.
  - Coverage results record no failing rows: 0 of 94 have a non-empty
    `failing_sample_keys`, across 5 fail, 74 pass and 15 warn.

---

## REQ-GEN-295

### [2] Criterion 2 by REQ-TEST-239's compare of a from-empty bootstrap before and after. **CAN'T TELL**
- **What is missing:** a "before" from-empty bootstrap, at the base commit
  before the restructure, to compare against. No such database exists.
  `select datname from pg_database` lists only `supply`, `supply_quarterly`,
  `supply_daily`, test, scratch and checkpoint databases. REQ-TEST-239's
  compare has not been run.
- **What does exist** is the generation-level substitute already recorded in
  evidence: the whole history generated at 39393c3 and at the build tree, every
  non-geocoding delivery file and receipt byte-identical. That is generation
  output, not the bootstrap compare the criterion names.

### [3] Criterion 7's confirmation after replay: REQ-GEN-186 criterion 3's comparison of every recorded geocoding target, green included, with the recorded verdicts. **MET**
- **The comparison covers the geocoding targets.** The quarterly bootstrap ran
  `bootstrap.targets_agree` (log line 9267: "Comparing every targeted supply's
  recorded verdict with what it was built to..."). Linkage Products'
  `target_datasets` is `(linkage-keys, *every geocoding dataset)`
  (`assets/quarterly/synthetic/collections/linkage_products.py:827-830`).
- **No disagreements.** A disagreement fails the run (`cli/pipeline.py`
  `_fail_on_disagreements`). The log has no "did not read as built" line
  (`grep -ci disagree` = 0) and ends `EXIT=0`.
- **Green targets are included.** Lines 9268-9272 are the comparison's
  "reported, never a failure" notes, which name planned greens:
  ```
  note: TS-93c's 2019-Q1 geo_cp_clients.csv (geo-cp-clients) was built to amber and its own checks agreed; the gate read red because of no cp_clients it could read
  note: the planned green for 2013-Q1 (geo-ed-presentations) was built to green and its own checks agreed; the gate read red because of no ed_presentations it could read
  note: the planned green for 2014-Q3 (geo-ed-presentations) ... 2025-Q2 ... 2026-Q2 (same wording)
  ```
- These five supplies agree by the criterion's own rule (their own checks
  match the target), but on the page they read red because their ED or Client
  Register source was not readable when they were checked. The 2013-Q1 one was
  later cleared by a knock-on (`left_out` marks it `2013-Q1*`); the others stay
  red. Worth knowing; not a disagreement.

---

## REQ-PIPE-296

### [4] Criterion 3: a geocoding delivery filed, staged, checked with all four tools, recorded and gated as its own package. **MET (one flag)**
- **Filed.** `select dataset_id, classification, count(*) from qa.filing where dataset_id like 'geo%' group by 1,2`
  gives geo-cp-clients early 43 and late 2; geo-ed-presentations early 50 and
  late 5.
- **Checked and recorded.** `select dataset_id, tool, count(distinct run_key), count(*) from qa.check_result where dataset_id like 'geo%' group by 1,2`:
  ```
  geo-cp-clients|dbt|45|135   evidently|45|45   file|45|270   soda|46|358   unrunnable|2|4
  geo-ed-presentations|dbt|55|165   evidently|55|55   file|55|330   soda|58|434   unrunnable|7|14
  ```
- **FLAG, datacontract-cli.** It ran on every geocoding run, but no check was
  asked of it. `qa.tool_output` holds a `datacontract` row for every geocoding
  and linkage run (166 each for datacontract, dbt, soda and evidently), and its
  raw output is `{"asked": []}`. `linkage-products-contract.yaml` declares no
  `quality:` blocks, so datacontract records no `check_result` for geo-* (or for
  linkage-keys, built earlier). Whether "checked with all four tools" means
  "run" or "contributed a check" is Keith's reading. On "run", it is met.
- **Gated as its own package, waiting on no linkage delivery.**
  `qa.gate_application` 65 (`DCP_20170501`, linkage) and 66
  (`daily_extract_may2017`, geocoding) are separate package entries for
  2017-Q2. Geocoding's hold, decision 134, names a missing ED Presentations
  source, not a linkage release.
  - Four geocoding promotions list a linkage-keys supply in `promoted_with`.
    Each is a shared knock-on release, e.g. gate_application 68 (`entry=knock-on`)
    promoting both after ED arrived, not a shared package.

### [5] Criterion 4: the bootstrap replaying the geocoding deliveries in receipt order with Child Protection, Emergency Department and the linkage deliveries. **MET**
- The bootstrap started from an empty database (log line 3, "Checking what this
  environment already holds...", then full generation; caller's statement).
- **Receipt order, checked across every arrival run** (not trial, not
  knock-on):
  ```sql
  with r as (select r.run_key, r.dataset_id, r.run_seq, sr.received_instant ri
    from qa.run r join qa.supply_receipt sr on sr.dataset_id=r.dataset_id and sr.supply_id=r.supply_id
    where not r.trial and r.caused_by_decision is null and r.caused_by_load is null),
  w as (select *, max(ri) over (order by run_seq rows between unbounded preceding and 1 preceding) prevmax from r)
  select count(*), count(*) filter (where ri < prevmax), count(*) filter (where dataset_id like 'geo%') from w;
  ```
  Result: `489|3|100`. That is 489 arrival runs, 100 of them geocoding, across
  child-protection, emergency-department and linkage-products, run in one
  sequence.
- The only 3 out-of-order runs are `cp_investigations`, `cp_notifications` and
  `cp_placements` of `Data Extract 01 Nov 2020`, all inside one delivery. They
  sit behind its `cp_clients`, whose receipt is the delivery's second (TEST)
  file, 10 minutes later. **No geocoding run is out of order.**
  - Every arrival run has a receipt (the anti-join count is 0).

### [6] Criterion 5: a geocoding delivery omitting one dataset's file leaves that slot unfilled, the other filed and checked. **MET**
- Geocoding deliveries holding only one dataset (from `qa.delivery_file`): 13
  geo-ed-presentations only, 3 geo-cp-clients only.
- In **2015-Q2 and 2015-Q3** the geocoding delivery (`Data Extract 01 May 2015`
  and `EXTRACT_20150811`) carries `geo-ed-presentations` alone.
  - The ED file is filed (early and late) and checked, with 18 results each.
  - geo-cp-clients has no filing for those slots, and its slot stays unfilled
    until a scripted `mark-not-supplied` decision for 2015-Q2, Q3 and Q4.
- In **2026-Q1** `REG_20260201` carries `geo-cp-clients` alone.
  - The Client Register file is filed, checked (18 results) and promoted
    (`qa.slot_holds_now`: decision 575).
  - `select count(*) from qa.filing where dataset_id='geo-ed-presentations' and slot='2026-Q1'`
    returns 0, and `slot_holds_now` has no row for geo-ed-presentations
    2026-Q1. It is an unfilled slot.
- The deferral note named "2015-Q2 to 2016-Q1" as the geo-ed-only quarters. The
  recorded data puts them at 2013-Q1 to 2015-Q3. geo-cp-clients' first period is
  2016-Q1 (`qa.run` min period), so only 2015-Q2 and Q3 are omissions of a
  dataset that is otherwise owed.

### [7] Criterion 6: each geocoding dataset shown on the dashboard like every other dataset. **MET**
- `reports/quarterly/doh_linkage-products_dashboard.json` holds `geo-cp-clients`
  ("Client Register Geocodes") and `geo-ed-presentations` ("ED Presentations
  Geocodes"). Each has the same keys as `linkage-keys`: `slotTimeline`,
  `runStates`, `promotedHealth`, `periodSlots`, `lastArrival`, `closedSlots`,
  `lateSlots` and the rest.
- **Real browser, 5ff97f93 e2e.**
  - `TestTheGeocodingPages`: 12 tests passed.
  - `TestStatusMatchesEachToolsOwnVerdict`: 3 passed, plus its daily twin's 3.
    It compares every rendered status with the recorded verdict.

### [8] Criterion 7: the from-empty bootstrap measured before and after, by collection and stream, recorded here and in CLAUDE.md's running log. **NOT MET**
- **Only the "after" exists.** Quarterly: 6666s wall clock; "Took Child
  Protection and Emergency Department and Linkage Products 6242s, in total
  6653s"; "OVER BUDGET ... 5946s over" (log lines 9266 and 9273). Daily: 681s,
  within budget.
- **What is missing:**
  - a "before" from-empty quarterly bootstrap without the geocoding datasets;
  - a split by collection and stream, since the log gives the three quarterly
    collections as one figure;
  - the geocoding runs and knock-ons counted separately;
  - the record in this requirement's evidence and in CLAUDE.md's running log
    (its last entry is REQ-PIPE-336's 1439s to 3509s).
- **The counts the "after" side would need can be read now**: 105 geocoding
  arrival runs, and 5 geocoding knock-on runs (`qa.run` joined to `qa.decision`
  on `caused_by_decision`).
- **The "before" is no longer a clean baseline.** Post-build-review #318 found
  generation slowed (906s profiled for one `arrivals_of` call) and fixed part of
  it after this bootstrap. A before/after taken now would mix the two changes.

### [9] Criterion 8: CI's deployment half run against a bootstrap holding the geocoding datasets, its duration recorded against REQ-TEST-260's allowance. **NOT MET**
- No `test.yml` has been started by hand since the build (caller). Push CI
  (`critical.yml`) runs no deployment half.
- **Missing:** a hand-started `test.yml` run, and its `test-deployment` job
  duration recorded. I have no GitHub access to confirm either way.

---

## REQ-QAC-297

### [10] Every check here recorded for a replayed geocoding supply: status, samples by id_1 and census_year, and the set it was judged against. **MET**
- **Every check is recorded with a status on every geocoding run.** For example,
  geo-cp-clients over 45 dbt and soda runs:
  - the three `census_year.*_set_members_dbt` checks: pass and fail;
  - `id_1.expected_ids_soda` and `id_1.no_surplus_ids_soda`;
  - `match_level.invalid_count_soda`, `sa2_code.invalid_count_soda` and
    `lga_code.invalid_count_soda`;
  - `match_level.value_share_soda`: pass, warn and fail;
  - `match_level.drift_psi_evidently`: pass, warn, fail and nodata;
  - `cp-clients.coverage_soda` and `cp-clients.referential_soda`.

  geo-ed-presentations has the same set, 55 runs each.
- **Samples by id_1 and census_year.** Every soda and dbt result on geo-* has
  `failing_sample_key_columns = ["id_1","census_year"]`, and every failing
  row-level check carries samples:
  ```
  geo-cp-clients duplicated 1/1, missing 1/1, unexpected 2/2 sampled; geo-ed-presentations duplicated 2/2, unexpected 1/1, referential 1/1 sampled
  geo-cp-clients|unexpected_set_members_dbt|fail|[["CPS-149176682", "2026"], ["CPS-328501547", "2026"], ["CPS-829989464", "2026"]]
  ```
  Share, coverage and drift failures carry none, by design: they are a
  percentage or a distribution.
- **The set judged against.** Every one of the 300 year-check results (`%set_members_dbt`
  on geo-*) carries `member_set`, `member_set_version` and `member_set_added`.
  The count of results missing any of the three is 0.
- **The share bands as specified.** `value_share_soda` pass max 4.55%, warn
  6.26-8.98%, fail 16.70%, with warn_threshold 5 and fail_threshold 10.

---

## REQ-GEN-298

### [11] Criterion 15 (2)'s second half: the trial of TS-100c's quarter agrees with the results the replay records for the same supply. **MET**
- **The trial.** At generation, the bootstrap tried
  `trial_20261103t031303710257z: geo_cp_clients: 1038 rows -> ...geo_cp_clients__201908011817000800`
  (log line 337), and generation went on. `trial_reads_agree` refuses on any
  disagreement.
  - The trial's half is also a real test outcome:
    `tests/test_geocoding_trial.py::TestARealTrialInItsPeriod::test_2_a_held_source_is_not_staged_and_its_readers_are_not_evaluated`
    passed on 5ff97f93 (`junit_16.xml`, 183s). It asserts both cp-clients-reading
    checks are not evaluated with `unrunnable_tables == ["cp_clients"]`, and
    the year checks are evaluated and pass.
- **The replay**, for `geo_cp_clients__201908011817000800`:
  ```
  cp-clients.coverage_soda|unrunnable|fail|["cp_clients"]
  cp-clients.referential_soda|unrunnable|fail|["cp_clients"]
  census_year.duplicated/missing/unexpected_set_members_dbt|dbt|pass
  ```
  This is the same reading: source checks not evaluated, naming `cp_clients`,
  and the year checks evaluated.

### [12] Criterion 8's "what it shows": TS-93c, TS-100c and TS-101b recorded could-not-run, held back, and TS-100c and TS-101b cleared by the knock-on. **MET**

| Scenario | Supply | Could-not-run | Held back | Knock-on | Outcome |
|---|---|---|---|---|---|
| TS-93c (2019-Q1) | `geo_cp_clients__201902011843000800` | coverage and referential `unrunnable` naming `cp_clients` | decision 224 `promotion-withheld` | none | no later decision; held for the rest of the history |
| TS-100c (2019-Q3) | `geo_cp_clients__201908011817000800` | `unrunnable` | decision 244 `promotion-withheld` | `__r1` (decision 246, cp-clients promote): both checks soda pass | decision 248 `promote` amber |
| TS-101b (2021-Q4) | `geo_ed_presentations__202111011850000800` | both `unrunnable` | decision 354 `promotion-withheld` | `__r1` (decision 357): both pass | decision 358 `promote` amber |

### [13] Criterion 13's measurement reported with REQ-PIPE-296's: the trials' wall clock in a from-empty quarterly bootstrap against REQ-PIPE-250's budget. **NOT MET**
- **The figure exists.** Log line 583: `Tried 43 supplies in their slots' periods in 53s on 4 worker(s)`.
  That is inside a 6666s quarterly bootstrap with a 720s budget. The criterion
  estimated "about 48" trials and "about 3 minutes" in parallel.
- **Missing:** the report itself, alongside REQ-PIPE-296's before/after
  measurement. That measurement does not exist ([8]), and the 53s is not yet in
  either requirement's evidence.

### [14] Criteria 3 and 4 on the dashboard: each scenario's check reading Warn or Fail for its own reason, and TS-111's Client Register carrying the Warn tag from the geocoding promotion. **NOT MET (two scenarios)**
- **Each scenario's own check does read Warn or Fail for its reason.** Recorded
  non-pass results per scenario supply:
  ```
  TS-102 geo_cp_clients__202305011830000800  missing_set_members=fail       (17/18 pass)
  TS-103 geo_ed_presentations__202202011830000800 duplicated_set_members=fail (17/18)
  TS-104 geo_cp_clients__201605011830000800  unexpected_set_members=fail    (17/18)
  TS-105 geo_ed_presentations__202302011830000800 value_share=warn(7.43)    (17/18)
  TS-106 geo_cp_clients__202402011830000800  value_share=fail(16.70)        (17/18)
  TS-107 geo_ed_presentations__201402011830000800 coverage=warn(99.21); drift_psi=fail(0.00)   (16/18)
  TS-108 geo_cp_clients__202502011830000800  coverage=fail(94.12)           (17/18)
  TS-109 geo_ed_presentations__201711011830000800 referential=fail          (17/18)
  TS-110 geo_cp_clients__202511011830000800  coverage=fail(0.00); drift_psi=nodata            (16/18)
  TS-111 geo_cp_clients__202602011830000800  coverage=warn(99.05); drift_psi=fail(0.00)       (16/18)
  ```
  The built JSON carries the same: for example "Census year present for every
  record" red on TS-102, "Share not geocoded" amber on TS-105, and the coverage
  check amber on TS-111.
- **TS-111's Client Register Warn tag is there.** In
  `reports/quarterly/cpfs_child-protection_dashboard.json`,
  `cp_clients__202511010100000000` is `promotedOn: green`, and its timeline
  turns `amber` at 2026-02-04T23:59:18 with cause "the promote of Client Register
  Geocodes" (period 2026-Q1). It is the only cp-clients supply coloured by a
  geocoding promotion. In a real browser,
  `TestTheGeocodingPages::test_9_the_g1_route_tags_the_older_client_register_supply`
  passed on 5ff97f93. It asserts "Promoted, warning", the cause, and no tag the
  day before.
- **Why NOT MET.** Criteria 3 and 4 say each scenario is "the only fault in its
  supply with every other check green". TS-107 and TS-111 also show
  **Distribution drift as Fail**: `status=fail`, `metric_value 0`,
  `extra.measured_status = "pass"`, and `reference_gap` 2013-Q4 and 2025-Q4
  respectively ("compared with 2013-Q3, not 2013-Q4: 2013-Q4 has no accepted
  supply").
  - The quarter before each was not accepted. 2013-Q4's geo-ed supply was held
    for want of ED. 2025-Q4 is TS-110's empty file, a red that was refused.
  - So each of these two pages shows a second Fail beside the scenario's own
    Warn.
  - The target comparison does not catch this, because the gate reads a gap red
    as its measured status.
  - TS-110 also shows drift as Not evaluated (empty file), which is not green.
    It is arguably unavoidable for an empty file.
  - **For Keith:** move TS-107 and TS-111, or accept a reference-gap red
    alongside them.

---

## REQ-DASH-299

### [15] Criterion 15: every one of its eleven remaining browser proofs. **MET**
5ff97f93 e2e run (`junit_e2e.xml`, tests built from `supply_quarterly` and `supply_daily`). Every one passed, and none was skipped (the run's only 2 skips are elsewhere):

| Proof | Test |
|---|---|
| (1) | `TestTheGeocodingPages::test_1_the_three_year_checks_read_as_three_problems_in_order` |
| (2) | `test_2_a_missing_year_is_a_constructed_line_never_a_row` |
| (3) | `test_3_a_duplicate_and_an_unexpected_year_say_what_they_are` |
| (4) | `test_4_the_census_years_tile_names_the_set_each_version_held`, 3 parametrised cases (2016-06-30, 2020-06-30, 2024-06-30), plus `test_4_no_tile_before_the_first_recorded_result` |
| (5) | `test_5_a_year_check_breaks_at_each_widening_in_the_history` |
| (6) | `test_6_the_geocodes_tile_links_its_source_and_match_level_has_value_bars` |
| (8) | `TestTheGeocodingPagesOnTheDailyAsset::test_8_another_collections_check_is_headed_by_its_phrase` |
| (9) | `test_9_the_g1_route_tags_the_older_client_register_supply` |
| (10) | `test_10_ed_presentations_shows_its_own_coverage_verdict` |
| (11) | `TestChecksThatReadAnotherCollection`, all 10 passed, including `test_the_not_supplied_quarter_reads_not_supplied_by_decision`; and `TestNotInTheAgreementOnThePage`, 2 passed |
| (12) | `test_12_the_agency_page_lists_across_collections` |

Each test asserts its precondition (a scenario period, a row) before inspecting it.

### [16] NFR 6, the render budget: page size and tests/test_dashboard_e2e.py's duration before and after. **NOT MET**
- **After only.**
  - `dashboard/qa-reporting-dashboard.html` is 1,175,176 bytes (built
    2026-11-03 11:08; it loads separate data files).
  - The e2e module ran in 1812.67s on 5ff97f93, run alone as one chunk, with 437
    tests.
- **Missing:** a "before" page size and e2e duration on a pre-REQ-DASH-299 tree
  against the same kind of database, and the comparison against the ~10% line.
- CLAUDE.md's last e2e module figures (717s, 659s and 667s, REQ-TEST-281) came
  from a different tree and database, so they are not a "before".

---

## REQ-QAC-300

### [17] Criterion 9 end to end: a year check's recorded result carrying member_set_version, member_set and member_set_added. **MET**
```sql
select dataset_id, regexp_replace(check_id,'^.*\.',''), status, extra->'failing_sample_keys',
       extra->>'member_set_version', extra->'member_set', extra->'member_set_added'
from qa.check_result where dataset_id like 'geo%' and tool='dbt' and status='fail' limit 12;
```
```
geo-cp-clients|unexpected_set_members_dbt|fail|[...]|2013-01-01|["2011"]|[]
geo-ed-presentations|unexpected_set_members_dbt|fail|[...]|2017-08-01|["2011", "2016"]|["2016"]
geo-cp-clients|duplicated_set_members_dbt|fail|[...]|2022-08-01|["2011", "2016", "2021"]|["2021"]
```
All 300 year-check results carry all three fields. The count of results
missing any of them is 0.

---

## REQ-QAC-340

### [18] Criteria 5 to 8 for recorded geocoding results. **CAN'T TELL (5, 6, 7 and 8's knock-on shown; 8's out-of-scope half not exercised)**
- **5, evaluated results count toward both supplies.** A geocoding coverage Warn
  coloured its source: cp-clients `cp_clients__202511010100000000` turns amber
  from "the promote of Client Register Geocodes" (built JSON
  `promotedHealth.timeline`).
- **6, not-evaluated counts toward the geocoding supply only.** The 2 geo-cp-clients
  and 7 geo-ed-presentations `unrunnable` results (TS-93c, TS-100c, TS-101b and
  the held ED quarters) coloured no source. In the built JSON, cp-clients has 1
  timeline entry caused by geo-cp-clients (the amber above) and ed-presentations
  has 0 caused by geo-ed-presentations.
- **7, the source is shown amber from the geocoding promotion's instant, not
  demoted, and as before earlier.** The same supply stays `promotedOn: green`,
  and turns amber at the promotion instant 2026-02-04T23:59:18. `test_9` passed
  in a real browser: tag present on the day, absent the day before.
  - No red-promoted source arose from geocoding. No geocoding red was promoted,
    so the red branch is not shown by data.
- **8, knock-on.** 5 geocoding re-checks were caused by source moves:
  geo-cp-clients from a cp-clients promote (1); geo-ed-presentations from
  ed-presentations promotes (3) and a refile (1).
- **8, out-of-scope: missing.** No geocoding supply exists in a period whose
  source is marked not supplied. cp-clients is marked not supplied only for
  2015-Q2, Q3 and Q4, where geo-cp-clients is itself marked not supplied. The
  rule is shown for linkage (scenario j, [15] proof 11), not for these checks.
  This half needs a geocoding supply in a source-not-supplied quarter, which the
  generated history does not hold.

### [19] Criterion 9: the checks shown on the source's page, the geocoding page and the agency page. **MET**
All passed on 5ff97f93 e2e:
- `test_9`, the source page: Client Register shows the geocoding cause.
- `test_10`, ED Presentations' own page: shows the geocoding coverage row and
  its Pass/Warn/Fail pill, and reads a drop as worse.
- `test_12`, the agency page: "Across collections" under Linkage Products,
  naming Child Protection's Client Register.
- `TestChecksThatReadAnotherCollection`: all 10.

The built JSON carries the checks on both sides: the cp-clients dataset JSON
mentions `geo-cp-clients` 308 times.

### [20] Criterion 11: REQ-TEST-339's thirty-dataset test with the fake geocoding datasets checked end to end. **CAN'T TELL**
`tests/test_thirty_linked_datasets.py::TestEachFakeGeocodingDatasetIsCheckedAgainstItsSource`
is not in any JUnit file of either run, because the module is on demand.
**Missing:** a run of that test.

---

## REQ-PIPE-341

### [21] Criterion 7: REQ-TEST-239's before-and-after compare of a from-empty bootstrap. **CAN'T TELL**
`tests/test_sample_keys_equivalence.py` is not in any JUnit file, because it
runs on demand. No "before" bootstrap database exists (see [2]).
**Missing:** two from-empty bootstraps, at the base tree and at the build tree,
and the compare between them.

### [22] NFR 1, the page asserted in a real browser. **MET**
On 5ff97f93 e2e:
- `TestASeveralColumnSampleOnTheRealPage::test_the_real_linkage_referential_results_name_their_records`
  passed (5.9s).
- Both tests of `TestASeveralColumnSampleOnTheRealPageOnTheDailyAsset` passed.

### [23] Criterion 8 at scale: the on-demand thirty-linked run records every linkage result under the whole key. **CAN'T TELL**
`tests/test_thirty_linked_datasets.py::TestEveryLinkageResultNamesItsRowsByTheWholeKey`
is in no JUnit file. **Missing:** a run of it.

For the real (non-fake) history, every linkage-keys referential result carries
`failing_sample_key_columns = ["dataset","id_1","id_2"]` ([1]). That is not the
thirty-dataset run.

---

## REQ-DASH-359

### [24] Criterion 4 in the built page: no colour word for a status in any text a person reads (REQ-TEST-361's guard). **MET**
On 5ff97f93 e2e, every test of the guard passed:
- `TestNoColourWordIsReadAsAStatus`: 4 passed
  (`test_every_tier_the_scenarios_tab_and_one_dataset_page_per_collection`,
  `test_a_column_panel_its_trend_tooltip_and_the_cross_table_grid`,
  `test_the_scenario_pages_every_named_surface_and_scenario_j`,
  `test_the_needs_action_queue_and_its_markers`);
- `TestNoColourWordIsReadAsAStatusOnTheDailyAsset`: 4 passed.

### [25] Criterion 14 in the built page: recorded text rendered inside its marked element, on pages carrying real recorded reasons and check changelog entries. **CAN'T TELL**
- **No real-browser test asserts it on a built page.** `[data-recorded-text]`
  appears in `tests/test_dashboard_e2e.py` only in the guard's skip list
  (`_GUARD_SKIPPED_MARKS`, line ~9306). The positive assertions are Vitest only:
  `tests-js/pass-warn-fail.test.js`, `rechecks.test.js` and
  `withdrawal.test.js`.
- **The guard passing proves nothing here.** No recorded text in either
  database contains a colour word:
  `select count(*) from qa.decision where reason ~* '\m(green|amber|red)\M'`
  returns 0 on `supply_quarterly` and 0 on `supply_daily`. The colour words in
  the check files are YAML comments. So the guard would pass whether or not the
  marks were present.
- **Missing:** a browser assertion that real decision reasons and changelog
  descriptions on the built page sit inside `[data-recorded-text]`.

### [26] Criterion 15 in the built page: colours, classes, data attributes and the grid's words unchanged, with TestStatusMatchesEachToolsOwnVerdict passing unchanged. **MET**
- **The test passed unchanged.** `TestStatusMatchesEachToolsOwnVerdict`: 3
  passed on 5ff97f93, plus its daily twin's 3. The class body is identical
  between 935e53b (before REQ-DASH-359) and HEAD. The first 209 lines diff
  clean; the only change is a new daily class after it.
- **Colours unchanged.** `git diff 935e53b HEAD -- dashboard/qa-reporting-dashboard.template.html`
  changes no `--good`, `--warn-fill`, `--warn` or `--bad` definition. The lines
  using `var(--bad)` and `var(--warn)` changed words only.
- **Status attributes unchanged.** `data-red-promoted`, `data-amber-promoted`
  and `data-amber-setting` appear in the same counts on removed and added lines.

### [27] Criterion 16, the e2e half and the NFR's scripted checklist. **NOT MET (the checklist half)**
- **The e2e half holds.** On 5ff97f93, `tests/test_dashboard_e2e.py` passed 436
  of 437. The one failure is the first-view budget test (load-sensitive, and not
  an assertion REQ-DASH-359 changed).
- **The checklist half is missing:** the per-phrase old/new counts over a built
  dashboard's visible text, before and after REQ-DASH-359. No such script output
  exists in the scratchpad, and no pre-REQ-DASH-359 built page was kept to
  count against.

---

## REQ-TEST-375

### [28] Criteria 4 to 7 and the Performance NFR on GitHub's runner. **CAN'T TELL**
- **What I can show.** `.github/workflows/critical.yml` triggers on push to
  `claude/**`. It sets `CRITICAL_BUDGET_SECONDS: "300"`, and its checker fails
  the job on zero tests, any skip or going over budget (lines 104-138). The
  caller reports runs 41692776303 and 41696483015 green, which by that checker
  implies under 300s with zero skips.
- **Missing:** reading those runs' Actions logs, both the critical and the JS
  job, for the measured pytest step time and the skip count. I have no GitHub
  access.

### [29] Criterion 8 on GitHub: a push starts no test.yml run, and a hand-started one still runs both halves and the coverage combine. **NOT MET (hand-started half not done)**
- **Configuration.** `.github/workflows/test.yml`'s `on:` is
  `workflow_dispatch:` only.
- **Push half: CAN'T TELL.** It needs GitHub's list of runs for a push.
- **Hand-started half: not done.** No hand-started `test.yml` has run since the
  build.

### [30] Criterion 9's floor on a full local gate: `mothman check` run whole with coverage enforced and its result line printed. **NOT MET**
- **No completed whole `mothman check` exists.**
  - `scratchpad/check.log` (2026-11-03 01:34) has no pytest row. It is a
    `--no-pytest` gate, which "Passed, with a warning from: schedule, sprints,
    scenario map".
  - `scratchpad/gate_final.log` (07:00) stops mid-`npm test`, and
    `gate_final_killed.log` was killed.
- **The nearest thing** is the chunked suite on 5ff97f93 with `--cov-append`,
  whose `coverage report --fail-under=92` gave TOTAL 94% and `COVRC=0`
  (`chunks_old/5ff97f93/driver.log`). That run had 2 failures and is not
  `mothman check`, so it printed no gate result line.
- **Missing:** one whole `mothman check` on a bootstrapped deployment, ending
  with its result line.

---

## Summary

| # | Requirement | Criterion | Verdict |
|---|---|---|---|
| 1 | REQ-QAC-333 | c6, referential failing rows as dataset code + identifiers | MET |
| 2 | REQ-GEN-295 | c2 by REQ-TEST-239's before/after bootstrap compare | CAN'T TELL |
| 3 | REQ-GEN-295 | c7 confirmation after replay (all geocoding targets) | MET |
| 4 | REQ-PIPE-296 | c3 filed, staged, four tools, recorded, own package | MET (flag: datacontract asked nothing) |
| 5 | REQ-PIPE-296 | c4 replay in receipt order with CP, ED, linkage | MET |
| 6 | REQ-PIPE-296 | c5 omitted file leaves slot unfilled, other checked | MET |
| 7 | REQ-PIPE-296 | c6 geocoding datasets on the dashboard like any other | MET |
| 8 | REQ-PIPE-296 | c7 from-empty bootstrap measured before and after | NOT MET |
| 9 | REQ-PIPE-296 | c8 CI deployment half with geocoding | NOT MET |
| 10 | REQ-QAC-297 | every check recorded: status, samples, set | MET |
| 11 | REQ-GEN-298 | c15(2) TS-100c trial agrees with replay | MET |
| 12 | REQ-GEN-298 | c8 TS-93c/100c/101b could-not-run, held, cleared | MET |
| 13 | REQ-GEN-298 | c13 trials' wall clock reported with PIPE-296's | NOT MET |
| 14 | REQ-GEN-298 | c3 and c4 on the dashboard, TS-111's Warn tag | NOT MET (TS-107, TS-111 carry a second Fail) |
| 15 | REQ-DASH-299 | c15 the eleven browser proofs | MET |
| 16 | REQ-DASH-299 | NFR 6 render budget before and after | NOT MET |
| 17 | REQ-QAC-300 | c9 member_set fields on recorded results | MET |
| 18 | REQ-QAC-340 | c5-8 on recorded geocoding results | CAN'T TELL (out-of-scope half unexercised) |
| 19 | REQ-QAC-340 | c9 on source, geocoding and agency pages | MET |
| 20 | REQ-QAC-340 | c11 thirty-dataset test with fake geocoding | CAN'T TELL |
| 21 | REQ-PIPE-341 | c7 REQ-TEST-239 before/after compare | CAN'T TELL |
| 22 | REQ-PIPE-341 | NFR 1 page in a real browser | MET |
| 23 | REQ-PIPE-341 | c8 at scale, thirty-linked run | CAN'T TELL |
| 24 | REQ-DASH-359 | c4 no colour word on the built page | MET |
| 25 | REQ-DASH-359 | c14 recorded text inside its mark on real pages | CAN'T TELL |
| 26 | REQ-DASH-359 | c15 colours, classes, attributes unchanged | MET |
| 27 | REQ-DASH-359 | c16 e2e re-run and the phrase checklist | NOT MET (checklist missing) |
| 28 | REQ-TEST-375 | c4-7 and Performance NFR on GitHub | CAN'T TELL |
| 29 | REQ-TEST-375 | c8 on GitHub | NOT MET (hand-started run not done) |
| 30 | REQ-TEST-375 | c9 full local `mothman check` with coverage | NOT MET |

**Totals: 15 MET, 8 NOT MET, 7 CAN'T TELL.**
