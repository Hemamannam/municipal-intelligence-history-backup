-- Owner ↔ property links with per-property evidence and units.
-- An owner may be linked via permits (owner of record on jobs) and/or
-- PLUTO (owner of record on the lot); relation preserves which.
select
    po.owner_id,
    po.property_id,
    po.relation,
    po.evidence_records,
    p.units_res,
    p.units_total,
    p.borough,
    p.zipcode
from {{ source('er', 'map_property_owners') }} po
join {{ ref('dim_property') }} p on p.property_id = po.property_id
