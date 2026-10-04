-- Q1: Complaints per building permit, by borough.
-- Why cross-dataset: complaint volume alone can't distinguish "neglected
-- building" from "building under active renovation" — permits provide the
-- denominator.
select
    borough,
    sum(complaints_12m) as complaints_12m,
    sum(permits_12m) as permits_12m,
    round(sum(complaints_12m) * 1.0 / nullif(sum(permits_12m), 0), 2)
        as complaints_per_permit_12m
from marts.mart_neighborhood_operations
group by borough
order by complaints_per_permit_12m desc;
