-- Property-level operational risk view: which buildings need attention.
-- This is a prioritization signal, not a claim of wrongdoing.
with base as (
    select
        p.property_id,
        p.canonical_address,
        p.borough,
        p.zipcode,
        p.units_res,
        p.year_built,
        coalesce(c.complaints_total, 0) as complaints_total,
        coalesce(c.complaints_12m, 0) as complaints_12m,
        coalesce(c.complaints_90d, 0) as complaints_90d,
        coalesce(c.complaints_prior_90d, 0) as complaints_prior_90d,
        coalesce(c.complaints_open, 0) as complaints_open,
        coalesce(c.complaints_emergency, 0) as complaints_emergency,
        c.avg_days_to_close,
        coalesce(pm.permits_12m, 0) as permits_12m,
        coalesce(pm.permits_total, 0) as permits_total,
        pm.total_estimated_cost,
        coalesce(b.businesses_active, 0) as businesses_active
    from {{ ref('dim_property') }} p
    left join {{ ref('int_property_complaints') }} c using (property_id)
    left join {{ ref('int_property_permits') }} pm using (property_id)
    left join {{ ref('int_property_businesses') }} b using (property_id)
    where coalesce(c.complaints_total, 0) + coalesce(pm.permits_total, 0)
          + coalesce(b.licenses_total, 0) > 0
)
select
    *,
    complaints_12m / nullif(units_res, 0) as complaints_per_unit_12m,
    case
        when complaints_prior_90d = 0 then null
        else round((complaints_90d - complaints_prior_90d) * 100.0 / complaints_prior_90d, 1)
    end as complaint_trend_pct,
    (complaints_90d >= 5 and permits_12m >= 2) as flag_active_work_with_complaints,
    (complaints_open > 0 and permits_12m > 0) as flag_open_complaints_new_permits
from base
