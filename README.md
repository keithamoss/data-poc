# Birth Registrations Pipeline

An actually-executable, end-to-end QA pipeline for the BDM Birth
Registrations feed — built to let you test dbt, Soda Core, datacontract-cli
and Evidently AI concepts against real generated data and real contract/
check files, and to replace the earlier QA reporting dashboard's fabricated
Birth Registrations numbers with genuinely computed ones. No part of this
pipeline's output is hand-typed or fabricated in the browser — every number
on the dashboard's Birth Registrations page traces back through this repo
to a real check evaluated against real generated CSVs.

Run it yourself:

```bash
./run_pipeline.sh
```

This regenerates 10 synthetic daily runs, loads them into DuckDB, runs all
four *equivalent* check engines (see below), and re-embeds the results into
`dashboard/qa-reporting-dashboard.html`. Every step is seeded, so re-running
reproduces the same runs and the same numbers.

To run the **real** tools instead:

```bash
pip install -r requirements-real.txt
pip install 'datacontract-cli[duckdb]'    # see requirements-real.txt - a second step, not optional
python3 real_tools/orchestrate_real.py    # -> reports/results_real.json
python3 real_tools/compare_real_vs_equivalent.py  # -> reports/comparison.txt
```

## What's real vs. "equivalent" — read this first

This repo has two generations. It started in a claude.ai session with **no
real internet access** (PyPI itself was unreachable there — every
`pip install` attempt returned "No matching distribution found"), so
`engines/*.py` are hand-written Python/DuckDB stand-ins for dbt-core, Soda
Core, datacontract-cli, and Evidently AI. A later Claude Code session, with
real internet access, installed and ran all four actual tools
(`real_tools/*.py`) against this same real data and real contract/check
files — confirming the equivalents were largely faithful, and surfacing
several genuine bugs in the original contract/schema files that only
running the real tools could find (see "Known simplifications and honest
disagreements" below).

**Both generations are real and kept.** The equivalents in `engines/`
remain a documented, dependency-free fallback; `real_tools/` is what
actually runs `dbt`, `soda`, `datacontract-cli`, and `evidently` today.

| Tool | What's real | Equivalent (engines/) | Real (real_tools/) |
|---|---|---|---|
| **datacontract-cli** | `contract/bdm-birth-registrations-contract.yaml` is a genuine ODCS v3.2.0 contract — `datacontract lint` passes on it. | `contract_engine.py`, a hand-written Python/DuckDB interpreter for the same real ODCS `metric`/`type: sql` rule vocabulary. | `run_datacontract_real.py` runs the actual `datacontract-cli` Python API (`DataContract.test()`) against each run's raw CSV via a `local` server. |
| **Soda Core** | `contract/bdm-birth-registrations-soda-checks.yml` is genuine SodaCL. | `soda_engine.py`, a hand-written interpreter for the same SodaCL shapes. | `run_soda_real.py` runs the real `soda-core` `Scan` API against a per-run DuckDB warehouse. |
| **dbt-core** | `dbt_project/` is a real dbt project — `dbt_project.yml`, a staging model, `schema.yml` with real generic tests and severity config. | `dbt_test_engine.py` renders the SQL model with actual Jinja2 into a DuckDB view, then evaluates the schema.yml tests as SQL. | `run_dbt_real.py` shells out to the real `dbt` CLI (`dbt run` + `dbt test`, dbt-duckdb adapter) against a per-run DuckDB warehouse. |
| **Evidently AI** | Population Stability Index (PSI) on the `sex` column vs. a reference run. | `drift_engine.py` computes PSI from scratch with the standard formula and 0.1/0.25 warn/fail bands. | `run_evidently_real.py` runs the real `evidently.Report` + `DataDriftPreset` (the current 0.7.x API). |

`requirements-real.txt` lists the exact package set verified to install and
run together — including a `pip check`-flagged conflict between
`soda-core-duckdb`'s declared `duckdb<1.1.0` ceiling and the actual duckdb
version (1.5.5) that all four tools were run against with no observed
breakage; see that file's comments before assuming the pip warning means
you must downgrade.

## Running it for real

Verified working end to end in this environment — not speculative:

1. `pip install -r requirements-real.txt`, then `pip install
   'datacontract-cli[duckdb]'` separately — a hard `pip` dependency
   conflict otherwise, not just a warning; see that file's comments.
2. `python3 real_tools/build_per_run_warehouses.py` builds one DuckDB file
   per run under `data/duckdb_runs/` (dbt and Soda each need a real
   warehouse to connect to, and get one file per run rather than the
   combined `data/warehouse.duckdb` — see that file's docstring for why).
3. `dbt run && dbt test --profiles-dir real_tools/dbt_profiles --project-dir dbt_project`,
   with `DBT_DB_PATH` set to one of those per-run files. The SQL model
   didn't need to change; `schema.yml`'s two custom-severity tests did —
   see its own comments and the disagreements section below for what real
   dbt-core actually required.
4. `soda scan -d birth_registrations -c real_tools/soda_configuration.yml contract/bdm-birth-registrations-soda-checks.yml` —
   the checks file itself never changed.
5. `datacontract lint` / `datacontract test` against
   `contract/bdm-birth-registrations-contract.yaml` — the contract *did*
   need real, structural fixes (also detailed below) before it would even
   lint.
6. `evidently` — a real `Report(metrics=[DataDriftPreset(columns=["sex"], cat_method="psi")])`
   comparing the reference run to each subsequent run.

Or just run `python3 real_tools/orchestrate_real.py`, which does all of the
above across every run and writes `reports/results_real.json`.

`engines/*.py` are kept as a working, dependency-free fallback per the
original handoff's request — not deleted now that the real tools run.

## Layout

```
contract/                    the two real YAML files, copied verbatim from this project's docs
generator/
  daily_batch.py              generates ONE day's birth-registration batch (an event-flow model,
                               deliberately different from the sibling synthetic-data-generator
                               repo's whole-population snapshot model — see the file's docstring)
  generate_runs.py             orchestrates 10 daily runs, 3 deliberately dirty, into data/raw/
  generate_cp_runs.py          orchestrates 10 weekly Child Protection snapshots into data/cp_raw/
  names_au.py, presentation.py, dirty.py   dirty.py has 2 new CP-specific presets;
                               kept in sync with synthetic-data-generator/dirty.py (see its docstring)
dbt_project/                 a real (if minimal) dbt project — dbt_project.yml, a staging model,
                               schema.yml with genuine two-tier severity config
engines/                     the Python/DuckDB equivalents (kept as a fallback)
  contract_engine.py           datacontract-cli equivalent
  soda_engine.py                Soda Core equivalent
  dbt_test_engine.py            dbt-core equivalent (renders the real SQL model via Jinja2)
  drift_engine.py                Evidently AI equivalent (real PSI)
real_tools/                  runs the actual dbt/soda/datacontract-cli/evidently tools
  build_per_run_warehouses.py   one DuckDB file per run, for dbt/Soda to connect to
  dbt_profiles/profiles.yml     dbt-duckdb connection profile (no secrets - just a path)
  soda_configuration.yml        Soda's data source config, for the `soda` CLI directly
  run_dbt_real.py                shells out to the real `dbt` CLI
  run_soda_real.py               runs the real soda-core Scan API
  run_datacontract_real.py       runs the real datacontract-cli Python API
  run_evidently_real.py          runs the real evidently.Report + DataDriftPreset
  orchestrate_real.py            all four, across every run -> reports/results_real.json
  compare_real_vs_equivalent.py  diffs results.json against results_real.json -> reports/comparison.txt
  cp_common.py                   shared agency/collection/dataset id constants for the 6 CP scripts below
  build_cp_warehouses.py         one DuckDB file per CP snapshot run, all 6 tables under a `raw` schema
  run_dbt_real_cp.py, run_soda_real_cp.py, run_datacontract_real_cp.py, run_evidently_real_cp.py
                                  the CP counterparts to the 4 birth-registrations real-tool scripts above
  orchestrate_real_cp.py         all four, across every CP run -> reports/results_real_cp.json
pipeline/
  load.py                       loads every generated run into one DuckDB table
  orchestrate.py                generate -> load -> all 4 equivalent engines -> reports/results.json
  build_dashboard_data.py       reshapes results.json into the dashboard's data shape
  build_cp_dashboard_data.py    reshapes results_real_cp.json into 6 datasets' worth of dashboard data
dashboard/
  qa-reporting-dashboard.html   the 3-tier QA dashboard, with Birth Registrations and the whole Child
                               Protection collection wired to real data
  embed_dashboard_data.py       re-embeds both real datasets (REAL_BIRTH_REG_DATA, REAL_CP_DATA) into the HTML
data/                          generated - raw run CSVs, manifest.json, warehouse.duckdb, duckdb_runs/,
                               cp_raw/, cp_duckdb_runs/ (not checked in)
reports/                       generated - results.json, results_real.json, results_real_cp.json,
                               birth_registrations_dashboard.json, child_protection_dashboard.json
                               (not checked in); comparison.txt is checked in
run_pipeline.sh                runs the equivalent-engine pipeline end to end
requirements-real.txt          the real tool packages - verified installing and running together
```

## The 10 runs

`generator/generate_runs.py` generates ten daily runs (2026-09-01 through
2026-09-10, ~1,800-2,000 rows each): seven clean, two deliberately
"amber", one deliberately "red" (run 4 and run 7 amber, run 9 red), using
`dirty.py`'s `apply_birth_registrations_presets()` — calibrated to land
exactly inside the Soda checks file's own warn/fail bands, not arbitrary
noise. Verified after generation, not just intended:

| Run | Severity | invalid `sex` rate | null `place_of_birth_facility` rate |
|---|---|---|---|
| run_01 (clean) | — | 0.0% | 2.1% |
| run_04 | amber | 0.8% | 21.1% |
| run_09 | red | 3.1% | 40.5% |

## The dashboard

Only **Registry Services → Civil Registration → Birth Registrations** is
wired to this pipeline's real output — tagged "Real pipeline data" on that
dataset's row and drawer. Every other dataset on the page except the Child
Protection collection (see below) is untouched: the same illustrative,
browser-fabricated mock data as before, still clearly labeled as such in
the footer. Each real column's drawer shows every check that actually ran
on it, across all four *equivalent* engines side by side (the real-tool
results live in `reports/results_real.json`/`comparison.txt` rather than
the dashboard, which was built against the equivalents first) — e.g. `sex`
shows Soda's `invalid_percent`, the contract's `invalidValues`, dbt's
`accepted_values`, Soda's scoped last-24h check, *and* the drift engine's
PSI, all computed independently against the same real data, so you can see
where different tools agree and where their models genuinely differ (see
below) — e.g. `place_of_birth_facility`'s Soda check reports a percentage
while its dbt check reports an absolute row count (a real dbt-duckdb
reliability issue forced that switch — see below), so the two numbers
won't visually match even though both come from the same 38-769 null
counts.

## The Child Protection collection

**Department for Child Protection and Family Support → Child Protection**
(6 datasets: Client Register, Notifications, Investigations, Placements,
Carer Register, Case Workers) is also wired to real output — but unlike
Birth Registrations, straight to the actual tools, not the equivalents:
`engines/*.py` are hard-coded single-table implementations with no
cross-table join support, and this collection's whole point is cross-table
checks (7 foreign-key relationships, 3 business rules spanning two tables
each), so retrofitting the equivalents for it would have been more work
than just running the real tools, which were already proven to work here.

```bash
python3 generator/generate_cp_runs.py       # -> data/cp_raw/ (10 weekly snapshots)
python3 real_tools/orchestrate_real_cp.py   # -> reports/results_real_cp.json
python3 pipeline/build_cp_dashboard_data.py # -> reports/child_protection_dashboard.json
python3 dashboard/embed_dashboard_data.py   # re-embeds BOTH real datasets into the HTML
```

A few things specific to this collection, each found by actually running
it end to end rather than assumed:

- **Generation model is different on purpose.** Birth Registrations is an
  event feed (a fresh cohort of newborns each day); Child Protection is a
  periodic *snapshot* extract of the same underlying casework collection,
  re-pulled weekly (`generator/generate_cp_runs.py`) — row counts stay
  roughly stable run to run, matching what a real active-caseload extract
  looks like.
- **The 7 FK relationship checks never fail on this fixture** — `dirty.py`'s
  CP presets never touch a foreign-key column, only `concern_type` (the
  traffic-light demo column, same role `sex` plays for Birth
  Registrations) and two business-rule-adjacent columns (`carer_id`,
  `end_date`). Kept as real checks anyway: a genuine backstop against a
  dropped join or truncated parent extract, not a check invented just to
  demonstrate something.
- **Two of the three business rules used to always fail**, on every run,
  dirty or clean — a real finding, not a bug in the rules:
  `synthetic-data-generator/child_protection.py` didn't originally enforce
  "a placement's carer must be Approved" or "a case can't close with an
  open investigation". Fixed at the generator level (both hold by
  construction on clean data now), with two new `dirty.py` presets
  (`apply_cp_placements_presets`, `apply_cp_investigations_presets`)
  reintroducing controlled violations on amber/red runs. See
  `plans/qa-pipeline.md` #9 for the full account.
- **A real dashboard display bug, caught by actually rendering this in a
  browser before calling it done**: `row_count` checks have
  `severity: warning` in the contract, so their real `fail_threshold` is
  `None` — and the dashboard's checks-building code defaults a missing
  `fail_threshold` to `0`, which made `checkStatus()` (`current > fail`)
  read any healthy positive row count as red. Fixed by excluding
  `row_count` from the per-column checks entirely
  (`pipeline/build_cp_dashboard_data.py`), the same way
  `build_dashboard_data.py` already handles Birth Registrations' rowCount
  rule (it only ever feeds the dataset's own `rowCount`/`prevRowCount`
  fields, never a column tile) — this bug was latent in that shared
  pattern the whole time, just never triggered until a check with
  `severity: warning` was shown as a column check.
- **Cross-table checks (the 7 FKs, the 3 business rules) have no single
  column to live on**, so they're grouped under a synthetic
  `(table-level checks)` pseudo-column per dataset rather than a new
  dashboard UI section — a deliberate scope trade-off, see
  `plans/wider.md` action 2.

## Known simplifications and honest disagreements

These are real properties of running four independently-designed check
systems against the same data, not bugs to paper over. The first group
below were only discoverable by actually running the real tools; the rest
held from the original equivalent-only build.

### Found by running the real tools

- **The original contract wasn't valid ODCS v3 at all, in five separate
  ways** — found by finally running `datacontract lint`/`test` for the
  first time. `description` must be an object (usage/purpose/limitations),
  not a bare string. `support` is itself the channel array, not wrapped in
  a `channels:` key. `team` is a single object with a `members:` list
  (v3.1.0+), and every member needs a `username`. `dimension` has a real,
  closed enum (accuracy/completeness/conformity/consistency/coverage/
  timeliness/uniqueness) — "validity" was never in it. And the whole
  `rule: nullCheck/regexPattern/validDateRange/validValues/fieldComparison/
  duplicateCheck/rowCount` vocabulary was invented — the real
  `DataQuality` model has no `rule` field (deprecated for `metric`) and no
  `mustBeRegex`/date-range-as-strings; the contract now uses the real
  `metric: nullValues/invalidValues/duplicateValues/rowCount` names plus
  `type: sql` custom queries for the two rules with no direct metric
  (date range, cross-field comparison). All fixed in the contract file
  itself, with comments explaining each. Also: datacontract-cli 1.2.0
  always lints against its *bundled* odcs-3.2.0 schema regardless of a
  contract's own declared `apiVersion` — found while chasing why a
  3.0.2-shaped `team:` kept failing against the real odcs-3.0.2 schema it
  matched exactly.
- **dbt-core's `error_if`/`warn_if` have no "%" syntax at all.** The
  original schema.yml's `error_if: ">2%"` looked like valid dbt config but
  is spliced verbatim into compiled SQL as `count(*) >2%` — a parser
  error, only visible once real `dbt test` actually ran it. A genuine
  percentage threshold needs a custom `fail_calc`. Real dbt-core also
  reserves `severity: warn` to mean "never escalate past warn" — the
  original schema.yml's `severity: warn` + `error_if` combination would
  have silently capped the sex/facility tests at warn forever, no matter
  how bad the data got, since dbt's own status logic only ever reaches
  "fail" when severity is the *default* "error". Both are documented in
  schema.yml's own comments.
- **A confirmed dbt-duckdb reliability bug, not a bug in this project's
  files.** Getting a genuine percentage threshold into `fail_calc`
  surfaced a reproducible case where dbt-core's own reported `failures`
  count was simply wrong — 0 instead of the true row count — on some runs,
  while the *identical* compiled SQL, executed directly via DuckDB's own
  Python API against the same file, always gave the right answer. This
  survived removing every layer of arithmetic (rounding, casting,
  percentage division, even a bare unmodified `count(*)`), disabling
  partial parsing, forcing `--store-failures`, and substituting `SUM` for
  `COUNT` — none of it was the cause, and no SQL-level explanation was
  found despite extensive isolation (documented in `schema.yml` and
  `real_tools/run_dbt_real.py`). The two affected tests now use absolute
  row-count thresholds instead of a computed percentage, and
  `run_dbt_real.py` independently re-verifies both tests' result via a
  direct query against the same warehouse dbt just tested, rather than
  trust a demonstrated-unreliable number — dbt-core still genuinely runs
  the real check; only the two known-unreliable numbers are cross-checked.
- **Soda's "last 24h" filter uses the real wall clock, and that changes
  the answer.** `filter birth_registrations [recent]: where:
  extract_timestamp >= CURRENT_DATE - 1` is evaluated faithfully by real
  Soda Core against `CURRENT_DATE` as of whenever the scan actually runs —
  not, as the equivalent engine assumed for lack of a real "now", each
  run's own latest `extract_timestamp`. Since every synthetic run's dates
  are in the past by the time this runs for real, the `[recent]` scope
  resolves to 0 rows on every run, and the scoped check always reports
  pass — including on run_09, where the equivalent's "as-of" simplification
  made it fail. Neither is wrong: the equivalent faithfully modeled "if
  this ran on the day of the extract"; real Soda faithfully modeled "if
  this ran today, on a fixture built for a different day."
- **Evidently's PSI and the equivalent's PSI genuinely differ, and both
  are correct.** Evidently's `DataDriftPreset` treats every distinct value
  actually observed in a column as its own category, so run_09's three
  different injected invalid `sex` codes ("9"/"U"/"O") count as three
  separate categories. `drift_engine.py`'s equivalent collapses everything
  outside {M, F, X} into one combined `_other` bucket. Both land in the
  same 0.1–0.25 "warn" band on run_09, but at different values (real
  Evidently: 0.144; the equivalent: 0.179) — PSI is genuinely sensitive to
  how a distributional shift is binned into categories.

### Held from the original build

- **The contract's `sex` rule and Soda's disagree on severity, correctly.**
  The ODCS contract's `invalidValues` rule has `severity: error` — any
  invalid value at all is a hard fail, confirmed by real `datacontract
  test` failing outright on run_04's 0.8% invalid rate (16 rows), not just
  run_09's 3.05%. Soda's `invalid_percent` check has a warn/fail *band*
  (warn > 0%, fail > 2%). Both are real, valid interpretations of "the
  same" business rule; the dashboard shows both, rather than forcing them
  to agree.
- **PSI doesn't always agree with the threshold-based checks.** On the
  deliberately "red" run, every threshold-based check (contract, Soda, dbt)
  correctly fails — but the drift engine's PSI for that run lands well
  inside the "warn" band, not "fail" (0.18 for the equivalent, 0.14 for
  real Evidently — see above). This is a genuine, expected property of PSI
  (it measures distributional *shift*, not "does any single value violate
  a rule") — not a miscalibration.
- **A single warn/fail threshold can't represent every real rule shape.**
  ODCS severity is single-tier (a rule is either strictly pass/fail, or
  pass/warn-only, never a three-way band); `contract_engine.py` encodes
  that into the dashboard's two-threshold shape as warn==fail (error
  severity) or an unreachable fail ceiling (warning/info severity) — see
  the comments in that file. Soda's `row_count` check is a genuine
  two-sided range (too few *or* too many rows); `soda_engine.py`'s
  `_numeric_threshold()` reduces it to the upper bound only for display,
  and this is the one place where a piece of real information (the lower
  bound) is dropped for the sake of a single scalar.
- **`source_system_record_id` and `extract_timestamp` now have real quality
  rules** (uniqueness/format, null/ordering-and-latency respectively),
  added along with a wider QA-check battery: format checks on 5 free-text
  columns, and a genuine cross-record consistency rule (every
  `is_multiple_birth` record must have a matching sibling row from the
  same birth event — `daily_batch.py` was fixed to actually generate that
  sibling row; see `plans/qa-pipeline.md`). Built real-tools-only (dbt-
  core/Soda Core/datacontract-cli, not `engines/*.py`) — most of it is
  nonetheless computed correctly by the existing equivalent engines too,
  since `contract_engine.py`/`dbt_test_engine.py` generically interpret
  whatever's in the shared contract/schema files. The genuine gaps
  (`soda_engine.py` has no `duplicate_count`/`failed rows`/`valid regex`
  support, `dbt_test_engine.py` has no singular-test support) are filled
  in on the dashboard from `real_tools/orchestrate_real.py`'s own output —
  see `pipeline/build_dashboard_data.py`'s merge comment for the full
  account, including a real false-positive this surfaced and fixed along
  the way (`soda_engine.py`'s `invalid_percent` handler silently treated
  an unrecognised `valid regex` check as "0 valid values", reporting every
  non-null value invalid).
- **No `relationships` dbt test between different tables.** This dataset
  is a single table with no other loaded model to join against (unlike
  synthetic-data-generator's Child Protection collection, which has real
  FKs across 6 tables) — adding one here would mean fabricating a join, so
  it's left out. The new `multiple_birth_sibling` dbt test is a *self*-join
  within this one table instead, which needs no second model.
- **Arrival timing is real but not very interesting**: every synthetic
  run's extract lag is generated under 20 hours, comfortably inside the
  contract's 24-hour SLA, so "on time" is always true in this fixture. It's
  a genuinely computed result (from real `extract_timestamp` values), not a
  hardcoded default — it just never gets to demonstrate a late-arrival
  scenario with the current generator.

## Relationship to the `synthetic-data-generator` repo

This is a separate, smaller repo, not a fork. It reuses
`names_au.py`/`presentation.py`/`dirty.py` unmodified (copied in under
`generator/`) for name pools, agency-specific ID presentation, and
failure-injection primitives. It does **not** reuse `population.py`'s
whole-population household model — `generator/daily_batch.py` is a
purpose-built event-flow generator instead, because a daily
birth-registrations extract is a fresh cohort of newborns each day, not a
resample of a static population snapshot. See that file's docstring for
the full reasoning.
