-- Real dbt singular test - REPLACES dbt_utils.recency (Phase 5f,
-- plans/qa-pipeline.md #61). That macro's "now" is always dbt.current_
-- timestamp() (real wall-clock time), with no way to parametrize it per
-- run - the honest reason this check was permanently red: this fixture's
-- dates are fixed to a window generated at some point in the past, and
-- every day real wall-clock time passes without a fresh regeneration,
-- CURRENT_DATE drifts further from it. The ODCS contract's matching
-- type: sql rule and the Soda checks file's matching `failed rows` check
-- have the same fix, same reason.
--
-- Each run's own DuckDB warehouse holds only that run's own batch
-- (see run_dbt_bdm.py's own docstring), and stg_birth_registrations
-- already carries date_registered as a real column - daily_batch.py
-- sets it to exactly this run's own run_date for every row (its own
-- comment: "this run's registrations cluster on run_date"). So "is
-- date_of_birth fresh" can be answered against THIS RUN's own date
-- instead of the real machine's clock, with zero new plumbing, and the
-- same anchor works identically for Soda (queries the same warehouse)
-- and datacontract-cli (date_registered is a real column of the raw CSV
-- it reads directly - no DuckDB-specific column needed).
--
-- NOT simply "date_of_birth close to date_registered, always": ordinary
-- registration lag (daily_batch.py's reg_lag_days, 0-9 days, on every
-- row regardless of any injected defect) already puts most rows within
-- 7 days of their own date_registered, so anchoring alone would make
-- this check trivially pass almost every run - no more meaningful than
-- the "always red" it replaces. generator/dirty.py's inject_stale_
-- delivery (an occasional whole-run defect, independent of severity
-- tier) is what gives this something real to fail on: on an
-- injected-stale run, EVERY row's date_of_birth gets pushed 15-45 days
-- before its own date_registered (well past the 7-day window), and this
-- test correctly goes red only then - date_registered itself is left
-- untouched by that injector, still reading as this run's own date.
select 1 as failing_row
where not exists (
  select 1
  from {{ ref('stg_birth_registrations') }}
  where date_of_birth >= date_registered - interval '7' day
)
