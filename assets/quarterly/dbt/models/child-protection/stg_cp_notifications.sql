with source as (
    select * from {{ source('raw', 'cp_notifications') }}
)

select * from source
