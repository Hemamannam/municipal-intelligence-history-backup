-- Canonical owner dimension (permit owners of record + PLUTO lot owners).
select
    owner_id,
    canonical_owner_name,
    owner_is_org,
    n_name_variants,
    n_properties,
    n_records
from {{ source('er', 'owners') }}
