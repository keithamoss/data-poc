with source as (
    select * from {{ source('raw', 'cp_case_workers') }}
)

select * from source
