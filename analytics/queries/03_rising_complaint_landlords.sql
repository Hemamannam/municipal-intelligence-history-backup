-- Q3: Landlords with rapidly increasing complaint rates (90d vs prior 90d).
-- Trajectory matters more than level for early intervention.
select
    canonical_owner_name,
    n_properties,
    total_units_res,
    complaints_90d,
    complaints_prior_90d,
    round((complaints_90d - complaints_prior_90d) * 100.0
          / nullif(complaints_prior_90d, 0), 1) as complaint_growth_pct
from marts.mart_landlord_performance
where complaints_prior_90d >= 5
order by complaint_growth_pct desc nulls last
limit 25;
