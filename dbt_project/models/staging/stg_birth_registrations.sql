-- Real dbt staging model SQL - would run as-is under `dbt run` once a real
-- adapter is wired to data/warehouse.db (see ../dbt_project.yml). Casts
-- is_multiple_birth back to boolean (SQLite has no native bool - the loader
-- stores it as 0/1) and gives the layer its conventional dbt name; every
-- other column passes through unchanged, since the source is already close
-- to analysis-ready.

with source as (
    select * from {{ source('raw', 'birth_registrations') }}
)

select
    registration_number,
    child_given_names,
    child_family_name,
    date_of_birth,
    sex,
    place_of_birth_suburb,
    place_of_birth_facility,
    date_registered,
    registering_parent_1_name,
    registering_parent_2_name,
    cast(is_multiple_birth as boolean) as is_multiple_birth,
    source_system_record_id,
    extract_timestamp,
    run_id,
    run_date
from source
