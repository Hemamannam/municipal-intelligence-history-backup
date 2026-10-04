-- Q8: Properties with open complaints followed by NEW permit activity —
-- work starting while tenant issues remain unresolved (inspection timing
-- signal: an inspector can see both at once).
select
    r.canonical_address,
    r.borough,
    r.units_res,
    r.complaints_open,
    c.complaints_emergency_open,
    r.permits_12m,
    p.last_permit_date,
    c.last_complaint_date
from marts.mart_property_risk r
join intermediate.int_property_complaints c using (property_id)
join intermediate.int_property_permits p using (property_id)
where r.flag_open_complaints_new_permits
  and p.last_permit_date > c.last_complaint_date - interval '90' day
order by c.complaints_emergency_open desc, r.complaints_open desc
limit 25;
