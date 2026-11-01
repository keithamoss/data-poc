-- Real dbt singular test: returns the rows that FAIL the rule (dbt fails
-- the test if this query returns anything). Cross-table business rule
-- approved alongside the 7 relationships tests in schema.yml - see
-- contract/child-protection-contract.yaml's matching type: sql version of
-- this same check for the full rationale and confirmed real numbers
-- (0 on clean runs, 2-3 on amber, 6 on the red run).
--
-- A notification recorded with outcome 'Investigation opened' must have a
-- matching cp_investigations row.

select n.notification_id
from {{ ref('stg_cp_notifications') }} n
left join {{ ref('stg_cp_investigations') }} i
    on n.notification_id = i.notification_id
where n.outcome = 'Investigation opened'
  and i.investigation_id is null
