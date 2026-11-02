-- A geocoding table's staging model (REQ-PIPE-296 criterion 2): the release as
-- delivered. Its year tests attach here and read the declared set in force for
-- the run's period through source() (REQ-QAC-297 criterion 3).
with source as (
    select * from {{ source('raw', 'geo_ed_presentations') }}
)

select * from source
