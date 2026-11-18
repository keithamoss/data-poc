-- The Cancer collection's singular test (REQ-QAC-348): a notification dated
-- before the diagnosis it reports. Passes (0 rows) on a clean supply - the
-- synthetic provider notifies each cancer after its diagnosis - and fails on a
-- red one, which moves a few notification dates before their diagnoses.

select notification_id, diagnosis_date, notification_date
from {{ ref('stg_cancer_notifications') }}
where cast(notification_date as date) < cast(diagnosis_date as date)
