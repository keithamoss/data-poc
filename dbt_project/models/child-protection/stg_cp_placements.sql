with source as (
    select * from {{ source('raw', 'cp_placements') }}
)

select * from source
