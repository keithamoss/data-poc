-- The Mental Health collection's one staging model (REQ-QAC-350): the supply as delivered.
with source as (
    select * from {{ source('raw', 'mental_health_contacts') }}
)

select * from source
