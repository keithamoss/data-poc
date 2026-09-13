-- Real dbt singular test - a freshness / relative-date check. See
-- contract/bdm-birth-registrations-contract.yaml's matching type: sql rule
-- (date_of_birth property) for the full rationale, including the honest
-- limitation this shares with the Soda checks file's [recent] filter: this
-- fixture's dates are fixed at Sept 2026, so this check reads as
-- increasingly failing the further real wall-clock time drifts from that
-- fixed window, independent of anything actually being wrong.
--
-- Unlike every other test in this project (which returns one row per
-- VIOLATION, so 0 rows = healthy), this check's healthy state is "at
-- least one row exists" - the query itself flips that back into dbt's
-- same "0 rows = pass" convention rather than needing a different test
-- shape: it returns exactly one row when NO record anywhere in the
-- warehouse has a date_of_birth within the last 7 days of the real
-- wall-clock date, and zero rows otherwise.

select 1
where not exists (
  select 1 from {{ ref('stg_birth_registrations') }}
  where date_of_birth >= current_date - interval 7 day
)
