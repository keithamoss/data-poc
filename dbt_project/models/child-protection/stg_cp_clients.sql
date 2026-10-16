-- Real dbt staging model - passthrough from the raw source, same
-- conventional layer stg_birth_registrations.sql gives that dataset. No
-- type coercion needed here (no booleans in this table, unlike
-- birth_registrations' is_multiple_birth).

with source as (
    select * from {{ source('raw', 'cp_clients') }}
)

select * from source
