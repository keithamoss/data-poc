with source as (
    select * from {{ source('raw', 'cp_carers') }}
)

select * from source
