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

This regenerates 10 synthetic daily runs, loads them into SQLite, runs all
four check engines, and re-embeds the results into
`dashboard/qa-reporting-dashboard.html`. Every step is seeded, so re-running
reproduces the same runs and the same numbers.

## What's real vs. "equivalent" — read this first

**dbt-core, Soda Core, datacontract-cli, and Evidently AI are not
pip-installable in the sandbox this repo was built in** (PyPI itself is
unreachable there — every `pip install` attempt returned "No matching
distribution found", and this was re-checked multiple times across this
project, not assumed). So this repo does not run those binaries. What it
does instead, for each one:

| Tool | What's real | What's a stand-in |
|---|---|---|
| **datacontract-cli** | `contract/bdm-birth-registrations-contract.yaml` is a genuine, unmodified ODCS v3 contract. `engines/contract_engine.py` parses and evaluates its actual rules (nullCheck, regexPattern, validDateRange, validValues, fieldComparison, duplicateCheck, rowCount). | The evaluator itself — a hand-written Python/SQLite interpreter for those rule types, not the `datacontract` binary. |
| **Soda Core** | `contract/bdm-birth-registrations-soda-checks.yml` is genuine SodaCL — real `warn:`/`fail:` syntax, `filter`/scoped-checks blocks included. `engines/soda_engine.py` evaluates it. | The evaluator — not the `soda` binary or its SodaCL parser. |
| **dbt-core** | `dbt_project/` is a real, structurally valid dbt project — `dbt_project.yml`, a staging model SQL file, `schema.yml` with real generic tests and `severity`/`warn_if`/`error_if` config. `engines/dbt_test_engine.py` renders the SQL model with **actual Jinja2** (the templating engine dbt itself uses) into a SQLite view, then evaluates the schema.yml tests as SQL against it. | `dbt run` / `dbt test` themselves — this project reads and executes the same files, just not through the dbt CLI. |
| **Evidently AI** | The statistic — Population Stability Index (PSI), the real metric Evidently's categorical drift preset reports, computed from scratch in `engines/drift_engine.py` with the standard formula and industry-standard 0.1/0.25 warn/fail bands. | The `evidently` library and its report/dashboard UI. |

If you get real internet access to this project — by linking this session
to a computer with the Claude desktop app, or by supplying pre-downloaded
wheels — `requirements-real.txt` lists the actual packages, and the section
below explains what to change (in most cases, nothing in the YAML/SQL files
themselves — only which program reads them).

## Running it for real, later

1. `pip install -r requirements-real.txt` on a machine with internet access.
2. Point `dbt_project/`'s (currently absent) `profiles.yml` and
   `pipeline/load.py`'s output at DuckDB or Postgres instead of SQLite — the
   engines all use plain `sqlite3`, which none of the real tools speak.
3. `dbt run && dbt test` against `dbt_project/` directly — the SQL and
   schema.yml don't need to change.
4. `soda scan -d birth_registrations -c configuration.yml contract/bdm-birth-registrations-soda-checks.yml` —
   the checks file doesn't need to change; you'll need a `configuration.yml`
   with real connection details (not included, since it depends on your
   warehouse choice).
5. `datacontract lint` / `datacontract test` against
   `contract/bdm-birth-registrations-contract.yaml` directly.
6. `evidently` — build a `Report` with a `DataDriftPreset` comparing the
   reference run to each subsequent run's `sex` column, in place of
   `engines/drift_engine.py`'s PSI computation.

None of `engines/*.py` need to keep existing once the real tools are
running — they were the bridge to get a genuinely working pipeline today.

## Layout

```
contract/                    the two real YAML files, copied verbatim from this project's docs
generator/
  daily_batch.py              generates ONE day's birth-registration batch (an event-flow model,
                               deliberately different from the sibling synthetic-data-generator
                               repo's whole-population snapshot model — see the file's docstring)
  generate_runs.py             orchestrates 10 daily runs, 3 deliberately dirty, into data/raw/
  names_au.py, presentation.py, dirty.py   reused unmodified from synthetic-data-generator
dbt_project/                 a real (if minimal) dbt project — dbt_project.yml, a staging model,
                               schema.yml with genuine two-tier severity config
engines/
  contract_engine.py           datacontract-cli equivalent
  soda_engine.py                Soda Core equivalent
  dbt_test_engine.py            dbt-core equivalent (renders the real SQL model via Jinja2)
  drift_engine.py                Evidently AI equivalent (real PSI)
pipeline/
  load.py                       loads every generated run into one SQLite table
  orchestrate.py                generate -> load -> all 4 engines -> reports/results.json
  build_dashboard_data.py       reshapes results.json into the dashboard's data shape
dashboard/
  qa-reporting-dashboard.html   the 3-tier QA dashboard, with Birth Registrations wired to real data
  embed_dashboard_data.py       re-embeds reports/birth_registrations_dashboard.json into the HTML
data/                          generated - raw run CSVs, manifest.json, warehouse.db (not checked in)
reports/                       generated - results.json, birth_registrations_dashboard.json (not checked in)
run_pipeline.sh                runs all of the above in order
requirements-real.txt          what to `pip install` once you have real internet access
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
dataset's row and drawer. Every other dataset on the page (Death/Marriage
Registrations, and everything outside Registry Services) is untouched: the
same illustrative, browser-fabricated mock data as before, still clearly
labeled as such in the footer. Each real column's drawer shows every check
that actually ran on it, across all four engines side by side — e.g. `sex`
shows Soda's `invalid_percent`, the contract's `validValues`, dbt's
`accepted_values`, Soda's scoped last-24h check, *and* the drift engine's
PSI, all computed independently against the same real data, so you can see
where different tools agree (they do, exactly, for `place_of_birth_facility`
— Soda and dbt report identical null rates, as they should against the
same table) and where their models genuinely differ (see below).

## Known simplifications and honest disagreements

These are real properties of running four independently-designed check
systems against the same data, not bugs to paper over:

- **The contract's `sex` rule and Soda's disagree on severity, correctly.**
  The ODCS contract's `validValues` rule has `severity: error` — any
  invalid value at all is a hard fail. Soda's `invalid_percent` check has a
  warn/fail *band* (warn > 0%, fail > 2%). Both are real, valid
  interpretations of "the same" business rule; the dashboard shows both,
  rather than forcing them to agree.
- **PSI doesn't always agree with the threshold-based checks.** On the
  deliberately "red" run, every threshold-based check (contract, Soda, dbt)
  correctly fails — but the drift engine's PSI for that run lands at 0.18,
  which is only "warn" by the conventional 0.1/0.25 PSI bands, not "fail".
  This is a genuine, expected property of PSI (it measures distributional
  *shift*, not "does any single value violate a rule") — not a
  miscalibration.
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
- **The Soda "last 24h" scoped check never actually excludes anything in
  this fixture.** `filter birth_registrations [recent]: where:
  extract_timestamp >= CURRENT_DATE - 1` is evaluated faithfully, but every
  synthetic run's `extract_timestamp` values are within a few hours of that
  same run's `date_registered` by construction — there's no multi-day-stale
  data in this fixture to exclude, so `[recent]` and the unscoped check
  currently agree. One place where they *don't* agree even so: run_07's
  clean-vs-dirty randomness happened to land at 1.03% invalid `sex` values,
  which fails the stricter 24h-scoped fail>1% threshold while only warning
  under the table-wide fail>2% threshold — a real example of scope
  changing the verdict.
- **`source_system_record_id` and `extract_timestamp` have no quality rule
  at all**, in the real contract or the real checks file. Rather than
  inventing one, the dashboard says so directly on those columns' drawers.
- **No `relationships` dbt test.** This dataset is a single table with no
  other loaded model to join against (unlike synthetic-data-generator's
  Child Protection collection, which has real FKs across 6 tables) — adding
  one here would mean fabricating a join, so it's left out.
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
