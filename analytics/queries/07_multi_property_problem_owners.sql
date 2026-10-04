-- Q7: Owners controlling multiple problematic properties (portfolio view).
-- One bad building is a building problem; five bad buildings under one
-- owner is a management problem.
with problem_properties as (
    select property_id
    from marts.mart_property_risk
    where complaints_per_unit_12m > 0.5 or complaints_open >= 5
)
select
    o.canonical_owner_name,
    lp.n_properties,
    count(*) as problem_properties,
    lp.total_units_res,
    lp.complaints_12m,
    lp.operational_risk_score
from problem_properties pp
join intermediate.int_owner_properties op on op.property_id = pp.property_id
join marts.dim_owner o on o.owner_id = op.owner_id
join marts.mart_landlord_performance lp on lp.owner_id = op.owner_id
group by o.canonical_owner_name, lp.n_properties, lp.total_units_res,
         lp.complaints_12m, lp.operational_risk_score
having count(*) >= 2
order by problem_properties desc, lp.operational_risk_score desc
limit 25;
