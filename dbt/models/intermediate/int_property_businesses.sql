-- Business-license rollup per property.
select
    property_id,
    count(distinct business_id) as businesses_total,
    count(distinct business_id) filter (where license_status = 'Active') as businesses_active,
    count(distinct business_category) as distinct_categories,
    count(*) as licenses_total
from {{ ref('stg_business_licenses') }}
where property_id is not null
group by property_id
