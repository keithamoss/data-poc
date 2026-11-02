-- Emergency Department's one staging model (REQ-QAC-231): the supply as delivered.
with source as (
    select * from {{ source('raw', 'ed_presentations') }}
)

select * from source
