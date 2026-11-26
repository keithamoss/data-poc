-- Real dbt singular test - see escalation_completeness.sql's header for
-- the pattern, and contract/child-protection-contract.yaml's matching
-- type: sql version of this check for the full rationale.
--
-- An investigation should not still be open (end_date NULL) once its
-- client's case_status is Closed. Passes (0 rows) on every clean run -
-- child_protection.py only ever marks a case Closed once none of that
-- client's own investigations are still open, so this holds by
-- construction. dirty.py's apply_cp_investigations_presets (amber/red
-- only) reopens a controlled number of Closed-case investigations to
-- demonstrate a real violation: 0 clean, 1-3 amber, 6 on the red run.
-- Previously (see plans/qa-pipeline.md #9) this test failed on every run
-- at a stable ~9% rate because the generator didn't tie case_status to
-- investigation state at all - fixed, not hidden.

select i.investigation_id, c.case_status
from {{ ref('stg_cp_investigations') }} i
join {{ ref('stg_cp_clients') }} c
    on i.cp_client_id = c.cp_client_id
where c.case_status = 'Closed'
  and i.end_date is null
