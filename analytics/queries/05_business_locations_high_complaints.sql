-- Q5: Licensed businesses operating at unusually complaint-heavy locations.
select
    canonical_business_name,
    categories,
    n_locations,
    active_licenses,
    location_complaints_12m
from marts.mart_business_activity
where active_licenses > 0
order by location_complaints_12m desc
limit 25;
