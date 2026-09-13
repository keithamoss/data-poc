-- Real dbt singular test - see escalation_completeness.sql's header for
-- the pattern, and contract/child-protection-contract.yaml's matching
-- type: sql version of this check for the full rationale.
--
-- REAL FINDING, not a bug in this test: currently fails on every run at a
-- stable ~9% rate (16/181 investigations on the base collection) because
-- child_protection.py generates case_status and investigation end_date
-- independently, with no invariant tying them together. Left in and
-- documented rather than hidden; tracked as a generator follow-up in
-- plans/qa-pipeline.md.
--
-- An investigation should not still be open (end_date NULL) once its
-- client's case_status is Closed.

select i.investigation_id, c.case_status
from {{ ref('stg_cp_investigations') }} i
join {{ ref('stg_cp_clients') }} c
    on i.cp_client_id = c.cp_client_id
where c.case_status = 'Closed'
  and i.end_date is null
