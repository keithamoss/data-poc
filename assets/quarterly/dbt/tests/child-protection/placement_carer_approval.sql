-- Real dbt singular test - see escalation_completeness.sql's header for
-- the pattern, and contract/child-protection-contract.yaml's matching
-- type: sql version of this check for the full rationale.
--
-- A placement's carer must be Approved, not Provisional or Under review.
-- Passes (0 rows) on every clean run - child_protection.py only ever
-- assigns an Approved carer to a placement, so this holds by
-- construction. dirty.py's apply_cp_placements_presets (amber/red only)
-- reassigns a controlled number of placements to a non-Approved carer to
-- demonstrate a real violation: 0 clean, 3 amber, 17 on the red run.
-- Previously (see plans/qa-pipeline.md #9) this test failed on every run
-- at a stable ~15% rate because the generator didn't enforce this
-- invariant at all - fixed, not hidden.

select p.placement_id, c.approval_status
from {{ ref('stg_cp_placements') }} p
join {{ ref('stg_cp_carers') }} c
    on p.carer_id = c.carer_id
where c.approval_status != 'Approved'
