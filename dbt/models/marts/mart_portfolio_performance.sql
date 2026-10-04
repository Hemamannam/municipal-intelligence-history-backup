{{ config(enabled=var('enable_portfolio_mart', true)) }}
-- Disable with --vars '{enable_portfolio_mart: false}' when HPD sources
-- are not ingested locally.
-- Portfolio-level performance: the answer to the customer's follow-up
-- ("LLC names hide portfolios"). Groups come from HPD registration
-- evidence (shared corporate owner / shared owner mailing address), so a
-- 40-building operation split across 40 LLCs rolls up to one row here.
with group_rollup as (
    select
        g.group_id,
        count(distinct g.property_id) as n_properties,
        sum(coalesce(p.units_res, 0)) as total_units_res,
        sum(coalesce(c.complaints_12m, 0)) as complaints_12m,
        sum(coalesce(c.complaints_open, 0)) as complaints_open,
        sum(coalesce(c.complaints_emergency, 0)) as complaints_emergency,
        sum(coalesce(pm.permits_12m, 0)) as permits_12m,
        count(distinct pr.pluto_owner_name) as distinct_owner_names
    from {{ source('er', 'property_owner_group') }} g
    join {{ ref('dim_property') }} p on p.property_id = g.property_id
    left join {{ source('er', 'properties') }} pr on pr.property_id = g.property_id
    left join {{ ref('int_property_complaints') }} c on c.property_id = g.property_id
    left join {{ ref('int_property_permits') }} pm on pm.property_id = g.property_id
    group by g.group_id
)
select
    r.group_id,
    og.group_label,
    r.n_properties,
    r.distinct_owner_names,
    r.total_units_res,
    r.complaints_12m,
    r.complaints_open,
    r.complaints_emergency,
    r.permits_12m,
    r.complaints_12m / nullif(r.total_units_res, 0) as complaints_per_unit_12m
from group_rollup r
join {{ source('er', 'owner_groups') }} og using (group_id)
