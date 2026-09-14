-- Real dbt singular test: returns the rows that FAIL the rule (dbt fails
-- the test if this query returns anything). Genuinely single-table/single-
-- column (unlike the 3 cross-table business rules this project's other
-- singular tests cover) - reuses the same "singular test, home table"
-- mechanism (cp_common.BUSINESS_RULE_HOME_TABLE) since it's already built
-- and correct for this shape too, not because this is a business rule.
--
-- Out-of-range date_of_birth - same rule as BDM's own ODCS date-range
-- check (contract/bdm-birth-registrations-contract.yaml), newly added
-- here since Child Protection had no equivalent. Count-based amber/red
-- band (not dbt's usual percentage, for the same dbt-duckdb fail_calc
-- reliability reason documented in schema.yml's header) - up to 10 bad
-- dates reads amber, more is a real problem. generator/dirty.py's
-- apply_cp_clients_presets is what makes this fail on amber/red runs
-- (clean runs never produce an out-of-range date_of_birth by
-- construction).

{{ config(warn_if = '>10', error_if = '>20') }}

select cp_client_id
from {{ ref('stg_cp_clients') }}
where date_of_birth < date '1900-01-01'
