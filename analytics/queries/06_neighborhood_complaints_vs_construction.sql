-- Q6: Neighborhood complaint pressure vs construction activity.
-- High complaints + low construction = neglect; high both = disruption.
select
    borough,
    zipcode,
    units_res,
    complaints_per_1k_units_12m,
    permits_per_1k_properties_12m,
    construction_cost,
    case
        when complaints_per_1k_units_12m > 400 and permits_per_1k_properties_12m < 50
            then 'high-complaint / low-investment'
        when complaints_per_1k_units_12m > 400
            then 'high-complaint / active-construction'
        else 'baseline'
    end as neighborhood_pattern
from marts.mart_neighborhood_operations
where units_res >= 1000
order by complaints_per_1k_units_12m desc
limit 30;
