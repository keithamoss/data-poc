-- Linkage Products' one staging model (REQ-QAC-330): the release as delivered.
-- A dbt test reading a linked table attaches here and reads it through
-- source() (REQ-PIPE-331 criterion 11).
with source as (
    select * from {{ source('raw', 'linkage_keys') }}
)

select * from source
