with source as (
    select * from {{ source('raw', 'cp_investigations') }}
)

select * from source
