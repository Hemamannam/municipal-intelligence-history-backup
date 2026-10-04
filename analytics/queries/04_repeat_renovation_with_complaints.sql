-- Q4: Properties receiving repeated permits while generating recurring
-- complaints — the "renovation pressure" pattern (possible tenant
-- displacement signal; framed as prioritization, not accusation).
select
    canonical_address,
    borough,
    units_res,
    complaints_12m,
    complaints_open,
    permits_12m,
    round(complaints_per_unit_12m, 2) as complaints_per_unit_12m,
    total_estimated_cost
from marts.mart_property_risk
where flag_active_work_with_complaints
order by complaints_12m desc
limit 25;
