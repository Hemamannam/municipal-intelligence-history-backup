-- Canonical property dimension. One row per resolved property; PLUTO
-- attributes where anchored, mention-derived attributes for standalones.
select
    property_id,
    bbl,
    canonical_address,
    house_number,
    borough,
    zipcode,
    latitude,
    longitude,
    units_res,
    units_total,
    pluto_owner_name,
    pluto_owner_is_org,
    year_built,
    bldg_class,
    in_pluto,
    n_mentions,
    n_source_records,
    created_at
from {{ source('er', 'properties') }}
