-- Real dbt singular test - a self-join within stg_birth_registrations
-- (the same model, referenced twice via two aliases - dbt's ref()
-- resolves to the same relation both times, so this genuinely joins the
-- table to itself). See contract/bdm-birth-registrations-contract.yaml's
-- matching type: sql version of this check (is_multiple_birth property)
-- for the full rationale.
--
-- Every is_multiple_birth record must have a matching sibling row from
-- the same birth event (same date_of_birth, facility, and registering
-- parent 1). Passes (0 rows) on every clean run - daily_batch.py's
-- generator fix (see plans/qa-pipeline.md) now actually generates a real
-- sibling row for every is_multiple_birth flag, rather than leaving it an
-- unenforced random flag. dirty.py's break_multiple_birth_siblings
-- (amber/red only) drops one twin from a fraction of real pairs to
-- demonstrate a real violation.

-- IS NOT DISTINCT FROM (not plain =) on place_of_birth_facility and
-- registering_parent_1_name: both can legitimately be null (home births;
-- the ~2% parent1-name null rate), and plain `=` against NULL is never
-- true in SQL even when both sides are the same NULL - found as a real,
-- live false-positive (4 flagged rows on a clean run where every sibling
-- pair genuinely matched) before switching to null-safe equality.
select a.registration_number
from {{ ref('stg_birth_registrations') }} a
where a.is_multiple_birth = true
  and not exists (
    select 1
    from {{ ref('stg_birth_registrations') }} b
    where b.is_multiple_birth = true
      and b.registration_number != a.registration_number
      and b.date_of_birth = a.date_of_birth
      and b.place_of_birth_facility is not distinct from a.place_of_birth_facility
      and b.registering_parent_1_name is not distinct from a.registering_parent_1_name
  )
