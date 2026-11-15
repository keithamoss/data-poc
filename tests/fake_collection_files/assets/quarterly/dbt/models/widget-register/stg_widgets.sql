-- REQ-TEST-249: the fake collection's one staging model.
with source as (
    select * from {{ source('raw', 'widgets') }}
)

select * from source
