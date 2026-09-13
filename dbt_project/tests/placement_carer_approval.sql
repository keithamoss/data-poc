-- Real dbt singular test - see escalation_completeness.sql's header for
-- the pattern, and contract/child-protection-contract.yaml's matching
-- type: sql version of this check for the full rationale.
--
-- REAL FINDING, not a bug in this test: currently fails on every run at a
-- stable ~15% rate (37/242 placements on the base collection) because
-- child_protection.py assigns carer_for_placement from the full carer
-- pool regardless of approval_status - the generator doesn't enforce this
-- invariant yet. Left in and documented rather than hidden; tracked as a
-- generator follow-up in plans/qa-pipeline.md.
--
-- A placement's carer must be Approved, not Provisional or Under review.

select p.placement_id, c.approval_status
from {{ ref('stg_cp_placements') }} p
join {{ ref('stg_cp_carers') }} c
    on p.carer_id = c.carer_id
where c.approval_status != 'Approved'
