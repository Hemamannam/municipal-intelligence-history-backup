-- Landlord (owner) performance + operational risk score.
--
-- SCORE METHODOLOGY (0-100, higher = higher priority for attention):
--   40%  complaints per residential unit (12m)   — burden on tenants
--   20%  emergency-complaint share               — severity
--   15%  open-complaint share                    — responsiveness
--   15%  complaint trend (90d vs prior 90d)      — trajectory
--   10%  permit churn per property (12m)         — construction pressure
-- Each component is percent-ranked across owners with ≥ 10 residential
-- units and ≥ 3 complaints (12m) so the score compares landlords against
-- peers, not against empty lots. This is an operational prioritization
-- score, NOT a legal or compliance judgment.
with owner_rollup as (
    select
        op.owner_id,
        count(distinct op.property_id) as n_properties,
        sum(coalesce(op.units_res, 0)) as total_units_res,
        sum(coalesce(c.complaints_total, 0)) as complaints_total,
        sum(coalesce(c.complaints_12m, 0)) as complaints_12m,
        sum(coalesce(c.complaints_90d, 0)) as complaints_90d,
        sum(coalesce(c.complaints_prior_90d, 0)) as complaints_prior_90d,
        sum(coalesce(c.complaints_open, 0)) as complaints_open,
        sum(coalesce(c.complaints_emergency, 0)) as complaints_emergency,
        avg(c.avg_days_to_close) as avg_days_to_close,
        sum(coalesce(p.permits_12m, 0)) as permits_12m,
        sum(coalesce(p.total_estimated_cost, 0)) as permit_cost_total
    from {{ ref('int_owner_properties') }} op
    left join {{ ref('int_property_complaints') }} c using (property_id)
    left join {{ ref('int_property_permits') }} p using (property_id)
    group by op.owner_id
),

scored_pool as (
    select
        *,
        complaints_12m / nullif(total_units_res, 0) as complaints_per_unit_12m,
        complaints_emergency / nullif(complaints_total, 0) as emergency_share,
        complaints_open / nullif(complaints_total, 0) as open_share,
        (complaints_90d - complaints_prior_90d) / nullif(complaints_prior_90d, 0) as trend,
        permits_12m / nullif(n_properties, 0) as permits_per_property_12m,
        (total_units_res >= 10 and complaints_12m >= 3) as in_scoring_pool
    from owner_rollup
),

ranked as (
    select
        *,
        percent_rank() over (order by coalesce(complaints_per_unit_12m, 0)) as r_cpu,
        percent_rank() over (order by coalesce(emergency_share, 0)) as r_emerg,
        percent_rank() over (order by coalesce(open_share, 0)) as r_open,
        percent_rank() over (order by coalesce(trend, 0)) as r_trend,
        percent_rank() over (order by coalesce(permits_per_property_12m, 0)) as r_permits
    from scored_pool
    where in_scoring_pool
)

select
    o.owner_id,
    o.canonical_owner_name,
    o.owner_is_org,
    s.n_properties,
    s.total_units_res,
    s.complaints_total,
    s.complaints_12m,
    s.complaints_90d,
    s.complaints_prior_90d,
    s.complaints_per_unit_12m,
    s.complaints_open,
    s.complaints_emergency,
    s.avg_days_to_close,
    s.permits_12m,
    s.permit_cost_total,
    s.in_scoring_pool,
    round(100 * (
        0.40 * r.r_cpu + 0.20 * r.r_emerg + 0.15 * r.r_open
        + 0.15 * r.r_trend + 0.10 * r.r_permits
    ), 1) as operational_risk_score
from scored_pool s
join {{ ref('dim_owner') }} o using (owner_id)
left join ranked r using (owner_id)
