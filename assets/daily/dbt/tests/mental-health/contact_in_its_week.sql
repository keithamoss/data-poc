-- The Mental Health collection's singular test (REQ-QAC-350): a contact more
-- than a week after the supply's earliest one. Passes (0 rows) on a clean
-- supply - the synthetic provider draws every contact from the seven days
-- before the Monday it is supplied - and fails on a red one, which dates a few
-- contacts a fortnight later.

with bounds as (
    select min(cast(contact_date as date)) as first_day from {{ ref('stg_mental_health_contacts') }}
)
select c.contact_id, c.contact_date
from {{ ref('stg_mental_health_contacts') }} c
cross join bounds b
where cast(c.contact_date as date) > b.first_day + 6
