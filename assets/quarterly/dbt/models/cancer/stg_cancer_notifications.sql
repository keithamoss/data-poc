-- The Cancer collection's one staging model (REQ-QAC-348): the supply as delivered.
with source as (
    select * from {{ source('raw', 'cancer_notifications') }}
)

select * from source
