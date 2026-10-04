-- Complaint rollup per property, with the time windows the marts need.
select
    property_id,
    count(*) as complaints_total,
    count(*) filter (where created_date >= current_date - interval '365' day) as complaints_12m,
    count(*) filter (where created_date >= current_date - interval '90' day) as complaints_90d,
    count(*) filter (
        where created_date >= current_date - interval '180' day
          and created_date < current_date - interval '90' day
    ) as complaints_prior_90d,
    count(*) filter (where not is_closed) as complaints_open,
    count(*) filter (where is_emergency) as complaints_emergency,
    count(*) filter (where is_emergency and not is_closed) as complaints_emergency_open,
    avg(days_open) filter (where is_closed) as avg_days_to_close,
    max(created_date) as last_complaint_date,
    count(distinct complaint_type) as distinct_complaint_types
from {{ ref('stg_311') }}
where property_id is not null
group by property_id
