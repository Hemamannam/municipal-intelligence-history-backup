-- Q2: Complaints per residential unit by landlord (12 months).
-- The headline cross-dataset question: needs 311 (complaints) + ER (who
-- owns what) + PLUTO (how many units) simultaneously.
select
    canonical_owner_name,
    n_properties,
    total_units_res,
    complaints_12m,
    round(complaints_per_unit_12m, 2) as complaints_per_unit_12m,
    operational_risk_score
from marts.mart_landlord_performance
where in_scoring_pool
order by complaints_per_unit_12m desc
limit 25;
