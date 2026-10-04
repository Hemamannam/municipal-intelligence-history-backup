-- Permit rollup per property.
select
    property_id,
    count(*) as permits_total,
    count(*) filter (where issued_date >= current_date - interval '365' day) as permits_12m,
    count(*) filter (where filing_reason ilike '%renewal%') as permits_renewals,
    count(distinct job_filing_number) as distinct_jobs,
    sum(estimated_job_cost) as total_estimated_cost,
    max(issued_date) as last_permit_date,
    count(distinct work_type) as distinct_work_types,
    count(distinct owner_name) as distinct_permit_owners
from {{ ref('stg_permits') }}
where property_id is not null
group by property_id
