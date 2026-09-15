-- Real dbt singular test - see multiple_birth_sibling.sql's header for
-- the pattern. Same rule as contract/bdm-birth-registrations-contract.
-- yaml's matching type: sql check on date_of_birth, and bdm-birth-
-- registrations-soda-checks.yml's matching `failed rows` check - added
-- together per plans/qa-pipeline.md #28's decision, so a PK-yielding
-- tool exists for this check (datacontract-cli's type: sql rules never
-- expose one). Named bdm_ (not cp_client_date_of_birth_range's bare
-- name) since both datasets have their own version of this same rule
-- shape and singular test files share one flat tests/ directory across
-- both dbt_project/ orchestration scripts.
--
-- Out-of-range date_of_birth - implausibly old, or in the future.

select registration_number, date_of_birth
from {{ ref('stg_birth_registrations') }}
where date_of_birth < date '1900-01-01' or date_of_birth > current_date
