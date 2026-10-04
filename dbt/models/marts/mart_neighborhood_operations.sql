-- Neighborhood (borough × ZIP) operational picture: complaint pressure vs
-- construction activity vs business presence.
with props as (
    select
        p.borough,
        p.zipcode,
        count(*) as properties,
        sum(coalesce(p.units_res, 0)) as units_res,
        sum(coalesce(c.complaints_12m, 0)) as complaints_12m,
        sum(coalesce(c.complaints_open, 0)) as complaints_open,
        sum(coalesce(c.complaints_emergency, 0)) as complaints_emergency,
        sum(coalesce(pm.permits_12m, 0)) as permits_12m,
        sum(coalesce(pm.total_estimated_cost, 0)) as construction_cost,
        sum(coalesce(b.businesses_active, 0)) as businesses_active
    from {{ ref('dim_property') }} p
    left join {{ ref('int_property_complaints') }} c using (property_id)
    left join {{ ref('int_property_permits') }} pm using (property_id)
    left join {{ ref('int_property_businesses') }} b using (property_id)
    where p.borough is not null and p.zipcode is not null
    group by p.borough, p.zipcode
)
select
    *,
    round(complaints_12m * 1000.0 / nullif(units_res, 0), 2) as complaints_per_1k_units_12m,
    round(permits_12m * 1000.0 / nullif(properties, 0), 2) as permits_per_1k_properties_12m
from props
where complaints_12m + permits_12m + businesses_active > 0
