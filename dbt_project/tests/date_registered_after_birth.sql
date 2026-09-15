-- Real dbt singular test - see multiple_birth_sibling.sql's header for
-- the pattern. Same rule as contract/bdm-birth-registrations-contract.
-- yaml's matching type: sql check on date_registered (a cross-field
-- consistency rule, not a format check - ODCS's "consistency" dimension),
-- and bdm-birth-registrations-soda-checks.yml's matching `failed rows`
-- check.
--
-- A registration date earlier than the birth date indicates a corrupt or
-- misjoined record.

select registration_number, date_registered, date_of_birth
from {{ ref('stg_birth_registrations') }}
where date_registered < date_of_birth
